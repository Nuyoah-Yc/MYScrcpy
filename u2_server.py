import asyncio
import io
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Optional

import uiautomator2 as u2
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from u2_webview import Webview as _U2Webview

SERVER_NAME = "AndroidUiAutomator2"
DEFAULT_SERIAL = os.getenv("U2_SERIAL")

# ── P0: IME keyboard package detection ──
_IME_PACKAGES = {
    "com.google.android.inputmethod.latin",
    "com.samsung.android.honeyboard",
    "com.baidu.input",
    "com.sohu.inputmethod.sogou",
    "com.iflytek.inputmethod",
    "com.tencent.qqpinyin",
    "com.touchtype.swiftkey",
    "com.microsoft.swiftkey",
    "com.android.inputmethod.latin",
    "com.huawei.ohos.inputmethod",
    "com.miui.inputmethod",
}


def _is_ime_package(pkg: str) -> bool:
    if not pkg:
        return False
    return pkg in _IME_PACKAGES or "inputmethod" in pkg or "keyboard" in pkg


# ── 系统对话框包：权限请求 / 安装 / 意图选择器等，必须全量显示且不做祖先去重 ──
_SYSTEM_DIALOG_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.android.documentsui",
    "com.google.android.documentsui",
    "com.android.intentresolver",
    "android",  # framework 对话框（chooser、credential 等）
}


def _is_system_dialog_package(pkg: str) -> bool:
    """判定节点是否属于系统弹窗（权限请求 / 安装 / 分享选择器等）。

    这类窗口通常覆盖在业务 app 之上，必须保留所有可点击元素，禁止被祖先去重策略过滤。
    """
    if not pkg:
        return False
    return (
        pkg in _SYSTEM_DIALOG_PACKAGES
        or "permissioncontroller" in pkg
        or "packageinstaller" in pkg
        or "intentresolver" in pkg
    )


# ── P1: class → semantic role mapping ──
_CLASS_ROLE_MAP = {
    "EditText": "input",
    "AutoCompleteTextView": "input",
    "MultiAutoCompleteTextView": "input",
    "TextInputEditText": "input",
    "SearchView": "input",
    "ExtractEditText": "input",
    "Button": "button",
    "MaterialButton": "button",
    "AppCompatButton": "button",
    "ImageButton": "button",
    "FloatingActionButton": "button",
    "CheckBox": "checkbox",
    "AppCompatCheckBox": "checkbox",
    "Switch": "switch",
    "SwitchCompat": "switch",
    "ToggleButton": "switch",
    "RadioButton": "radio",
    "SeekBar": "slider",
    "RatingBar": "slider",
    "Spinner": "dropdown",
}


# ── P0: activity → page breadcrumb ──
def _build_page_path(activity: str) -> str:
    """Parse activity name into human-readable breadcrumb, e.g. '.welcome.WelcomeTourActivity' → 'Welcome > WelcomeTour'"""
    if not activity:
        return ""
    act = activity.lstrip(".")
    parts = act.split(".")
    # Last part is the Activity class name
    name = parts[-1]
    # Remove 'Activity' and trailing app-specific suffix like 'Gmail'
    name = re.sub(r"Activity\w*$", "", name)
    # Build path: sub-packages (capitalized) + cleaned activity name
    path_parts = [p.capitalize() if p == p.lower() else p for p in parts[:-1]]
    if name:
        path_parts.append(name)
    return " > ".join(path_parts) if path_parts else act


mcp = FastMCP(
    name=SERVER_NAME,
    instructions=(
        "This MCP Server is based on uiautomator2 for Android device automation. "
        "Use get_screen to fetch visible elements on the current screen, "
        "then perform tap actions based on each element's text/desc/id."
    ),
)

_devices: dict[str, u2.Device] = {}
_current_serial: Optional[str] = DEFAULT_SERIAL  # 当前活跃设备序列号


def _get_device(serial: Optional[str] = None) -> u2.Device:
    """获取指定 serial 的设备连接，支持多设备并行操作。

    @param serial: 设备序列号（如 "emulator-5554"）。未指定时使用当前活跃设备。
    """
    key = serial or _current_serial or ""
    if key not in _devices:
        _devices[key] = u2.connect(key) if key else u2.connect()
    return _devices[key]


def _parse_bounds(bounds_str: str):
    m = re.findall(r'\d+', bounds_str)
    if len(m) == 4:
        return tuple(int(v) for v in m)
    return None


# 带条目回收机制的容器：已滑过的条目会从 dump 中消失，backward 方向判断不可靠
_RECYCLING_CLASSES = {"RecyclerView", "ListView", "GridView", "ViewPager", "ViewPager2"}


def _infer_can_swipe(node, direction: str, container_bounds: tuple, cls_short: str) -> list:
    """推断滑动容器仍可继续滑动的手指方向。

    返回 "up"/"down"/"left"/"right" 的子集，语义与 swipe/scroll_to_find 的 direction 一致：
      - "up"    手指向上 → 露出下方内容（forward）
      - "down"  手指向下 → 露出上方内容（backward）
      - "left"  手指向左 → 露出右侧内容
      - "right" 手指向右 → 露出左侧内容

    背景约束：Android AccessibilityNodeInfo 的 getBoundsInScreen 把所有 bounds
    都裁到"可见交集"。未显示的后代节点要么在 dump 里消失（回收型容器），要么
    bounds 被裁到容器可见区域（非回收型容器）。换言之，**没有任何后代节点的
    bounds 会越过容器边界** —— 任何基于"bounds 越界"的判断在 UiAutomator 层级
    里都是恒假的。因此分两类处理：

    1) 回收型容器（RecyclerView / ListView / GridView / ViewPager*）：
       只为当前视口内的条目创建 ViewHolder，dump 里的直接子项就是视口内真实
       出现的条目。最上/最下的"半露出"条目 bounds 会被裁到容器可见边，其 size
       会显著小于同视口内的完整条目。我们用
         size(edge) < typical * 0.98  AND  edge_attached_to_container_edge
       判定该方向是否还有内容可露出。
       - typical 取**中间项中的最小自然尺寸**（过滤掉 divider/spacer 类 outlier
         后的 min）。设置类 / section-header 类 RecyclerView 的子项尺寸天然
         异质（header 224、radio 300、switch 188、summary 254 等），若用
         max*0.98 作阈值，天然小尺寸的首/末项必然被误判为"被裁"；反过来用
         min*0.98 则把"最小合法自然尺寸"当作安全线，只有比它还小才算裁剪。
         同质列表里 min ≈ max，退化为原来的紧阈值，不影响原行为。
         过滤阈值 max*0.3：排除 RecyclerView 里可能出现的 1~n 像素 divider
         条目，避免 min 被 divider 拉到 ≈0。
       - edge_attached (tol=5) 区分"顶部 padding 下的天然 header 项"与
         "中部/底部被裁的半项"：顶部时容器 padding 会让首子项 top 与容器 top
         有几十像素间距（not attached），此时即便首项天然偏小也不视为被裁。

    2) 非回收型容器（ScrollView / NestedScrollView / HorizontalScrollView）：
       后代节点全在层级里，但 bounds 被裁到容器可见交集 —— size 信号不可用，
       越界检测恒假。UiAutomator dump 也不暴露 canScrollForward/Backward。
       **无法在 XML 层面可靠判定**。保守返回两个方向，既然容器已被识别为
       scrollable，调用方就应假设两侧都可能有内容，避免 scroll_to_find 因
       can_swipe=[] 提前退出。代价：一屏装下的短 ScrollView 会被错报为双向
       可滑（误报优于漏报）。
    """
    fwd, bwd = ("up", "down") if direction == "vertical" else ("left", "right")

    # ── 分支 1：回收型容器 —— 用边缘子项裁剪信号 ──
    if cls_short in _RECYCLING_CLASSES:
        kid_bounds = []
        for kid in list(node):
            b = _parse_bounds(kid.get("bounds", ""))
            if b:
                kid_bounds.append(b)

        if len(kid_bounds) >= 3:
            cx1, cy1, cx2, cy2 = container_bounds
            if direction == "vertical":
                sizes = [b[3] - b[1] for b in kid_bounds]
                first_start, last_end = kid_bounds[0][1], kid_bounds[-1][3]
                c_start, c_end = cy1, cy2
            else:
                sizes = [b[2] - b[0] for b in kid_bounds]
                first_start, last_end = kid_bounds[0][0], kid_bounds[-1][2]
                c_start, c_end = cx1, cx2

            # 典型自然项尺寸：中间项里过滤掉 divider/spacer 类 outlier 后取 min。
            #
            # 为什么是 min 而不是 max：设置/导航类 RecyclerView 里不同 item 类型
            # （header / radio / switch / summary / row）天然高度不同，max*0.98
            # 会把天然偏小的首/末项误判为"被裁"；min 代表"最小合法自然尺寸"，
            # 只有当边缘项比它还小时才确信是被裁。同质列表里 min ≈ max，
            # 退化为原来的紧阈值，不影响已通过场景。
            # outlier 过滤（< max*0.3）：排除 RecyclerView 中偶尔出现的 1~几像素
            # divider 条目，避免把 min 拉到 ≈0 让阈值失效。
            middles = sizes[1:-1]
            max_mid = max(middles)
            natural_middles = [s for s in middles if s >= max_mid * 0.3]
            typical = min(natural_middles) if natural_middles else max_mid

            # 容器内部项与容器边贴合判定。tol=5 覆盖整数取整误差，但小到足以区分
            # "顶部几十像素 padding 下的首项"（not attached）和"中部/底部被裁到 0
            # 间距的半露出项"（attached）。
            first_attached = abs(first_start - c_start) <= 5
            last_attached = abs(last_end - c_end) <= 5

            # 2% 阈值：边缘项比"最小自然尺寸"还小 ≥2% 才视为被裁，1% 以内
            # 视为整数取整误差。
            clipped_threshold = typical * 0.98
            first_clipped = first_attached and sizes[0] < clipped_threshold
            last_clipped = last_attached and sizes[-1] < clipped_threshold

            # 整屏装下的短列表：至少一端未贴合容器边（有空白），无需滑动。
            if not first_attached or not last_attached:
                return []

            # 4 case 组合（双端都贴合容器边时）：
            #
            #   first_clipped + last_clipped  → 中间：双端都有溢出 → [fwd, bwd]
            #   first_clipped only            → 接近底部：首项被裁（上方有内容）、
            #                                    末项完整（贴在容器底）→ [bwd]
            #   last_clipped only             → 接近顶部：末项被裁（下方有内容）、
            #                                    首项完整（贴在容器顶）→ [fwd]
            #   neither clipped               → 罕见对齐：长列表的 viewport 恰好
            #                                    与若干完整项对齐（无半项可裁）。
            #                                    XML 信号无法判断方向，与非回收型
            #                                    容器分支同策略：保守返回两个方向。
            #
            # 关键：第二个分支（first_clipped only → [bwd]）保证"滑到底部"时
            # can_swipe 严格不再含 fwd，符合调用方"列表到底就停"的期望。
            if first_clipped and last_clipped:
                return [fwd, bwd]
            if first_clipped:
                return [bwd]
            if last_clipped:
                return [fwd]
            return [fwd, bwd]

        # 子项太少（< 3）：无法确定 typical，保守返回两个方向。
        return [fwd, bwd]

    # ── 分支 2：非回收型容器 —— bounds 被裁，无可靠 size 信号 ──
    # 保守返回两个方向。详见 docstring。
    return [fwd, bwd]


def _select_element(d: u2.Device, step: dict):
    """根据 text/textContains/desc/descContains/id 构造 u2 selector，支持 index 和 bounds 区域过滤。

    - index: 当多个元素匹配时，选择第 N 个（0-based），默认 0。
    - bounds: 限定区域 "[x1,y1][x2,y2]"，只匹配中心点落在此区域内的元素。
    """
    if step.get("text"):
        el = d(text=step["text"])
    elif step.get("textContains"):
        el = d(textContains=step["textContains"])
    elif step.get("desc"):
        el = d(description=step["desc"])
    elif step.get("descContains"):
        el = d(descriptionContains=step["descContains"])
    elif step.get("id"):
        # 用 resourceIdMatches 兼容短 id（如 "subject"）和全限定 id
        # 注意：Android UiAutomator 的 resourceIdMatches 使用 Pattern.matches()（全字符串匹配），
        # 必须用 .* 前缀来跳过包名部分（如 "com.google.android.apps.maps:id/"）
        rid = step["id"]
        el = d(resourceIdMatches=rf"(.*:id/)?{re.escape(rid)}$")
    else:
        return None

    # bounds 区域过滤：只保留中心点在指定区域内的元素
    bounds_filter = step.get("boundsInside")
    if bounds_filter:
        box = _parse_bounds(bounds_filter)
        if box:
            matched = []
            for i in range(el.count):
                try:
                    info = el[i].info
                    b = info.get("bounds", {})
                    cx = (b.get("left", 0) + b.get("right", 0)) // 2
                    cy = (b.get("top", 0) + b.get("bottom", 0)) // 2
                    if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                        matched.append(i)
                except Exception:
                    pass
            if not matched:
                return None
            idx = step.get("index", 0)
            real_idx = matched[idx] if idx < len(matched) else matched[0]
            return el[real_idx]

    # index 支持：选择第 N 个匹配（0-based）
    idx = step.get("index", 0)
    if idx > 0:
        return el[idx]
    return el


# ── 屏幕解析（同步，通过 to_thread 调用） ──


def _get_visible_elements_sync(d: u2.Device, app_package: str = "", xml_str: Optional[str] = None) -> dict:
    """解析当前屏幕 UI 层级，返回可见元素列表和滑动区域。

    - 自动过滤输入法键盘元素（但上报 keyboard_visible）
    - 系统对话框（权限请求 / 安装 / 分享选择器等）必须全量输出且跳过祖先去重，
      并通过 system_dialog_visible 上报，提示调用方优先处理。
    - xml_str 可由上游（如 _dump_until_stable）预先抓取后传入，避免重复 dump。
    """
    if xml_str is None:
        xml_str = d.dump_hierarchy(compressed=True)
    root = ET.fromstring(xml_str)

    keyboard_visible = False
    system_dialog_visible = False

    parent_map = {child: parent for parent in root.iter("node") for child in parent}

    # 屏幕尺寸：取所有节点 bounds 的 max，比依赖特定 root 节点更稳
    # （compressed 模式下根 FrameLayout 会被合并掉）。
    _screen_w = 0
    _screen_h = 0
    for _n in root.iter("node"):
        _b = _parse_bounds(_n.get("bounds", ""))
        if _b:
            if _b[2] > _screen_w:
                _screen_w = _b[2]
            if _b[3] > _screen_h:
                _screen_h = _b[3]
    # 半屏阈值：祖先占屏幕 ≥50% 且不 clickable 时视为"页面容器"，其 text/desc
    # 不应被当作子节点的可见标签触发去重。典型受害者是 Compose 整屏 semantic
    # 容器（如 <LinearLayout desc="设置页面"> 覆盖整个 content 区）—— 原逻辑
    # 会让它吃掉所有真实 TextView 子项，get_screen 只剩 desc="设置页面" 一条。
    _page_container_min_area = (_screen_w * _screen_h) // 2

    # 预计算每个节点的祖先链属性，避免重复遍历
    _ancestor_has_text_cache: dict[int, bool] = {}
    _ancestor_clickable_cache: dict[int, bool] = {}

    def _compute_ancestor_flags(n):
        """一次遍历祖先链，同时计算 has_visible_ancestor 和 parent_clickable。"""
        nid = id(n)
        if nid in _ancestor_has_text_cache:
            return
        has_text = False
        has_click = False
        cur = parent_map.get(n)
        while cur is not None:
            if not has_text and cur.get("package") != "com.android.systemui":
                t = (cur.get("text") or "").strip()
                ds = (cur.get("content-desc") or "").strip()
                if t or ds:
                    # 排除"页面容器"型祖先：不 clickable 且占屏幕 ≥50%。
                    # 这类节点只是布局容器（尤其 Compose 整屏 semantic label），
                    # 不代表具体可交互元素，不应让其 label 覆盖内部真实子节点。
                    ab = _parse_bounds(cur.get("bounds", ""))
                    is_page_container = (
                        ab is not None
                        and cur.get("clickable") != "true"
                        and (ab[2] - ab[0]) * (ab[3] - ab[1]) >= _page_container_min_area
                    )
                    if not is_page_container:
                        has_text = True
            if not has_click and cur.get("clickable") == "true":
                has_click = True
            if has_text and has_click:
                break
            cur = parent_map.get(cur)
        _ancestor_has_text_cache[nid] = has_text
        _ancestor_clickable_cache[nid] = has_click

    elements = []
    for node in root.iter("node"):
        text = (node.get("text") or "").strip().replace("\xa0", " ").replace("\n", " ").replace("\t", " ")
        desc = (node.get("content-desc") or "").strip().replace("\xa0", " ").replace("\n", " ").replace("\t", " ")
        if not text and not desc:
            continue
        pkg = node.get("package", "")
        if pkg == "com.android.systemui":
            continue
        # P0: filter IME keyboard elements
        if pkg and pkg != app_package and _is_ime_package(pkg):
            keyboard_visible = True
            continue
        # 系统对话框（权限 / 安装 / 选择器）必须全量输出，跳过祖先去重。
        # 注意：不能用 `pkg != app_package` 排除 —— 当权限/安装页以全屏 Activity
        # 的形式前台展示时，d.app_current() 返回的就是 permissioncontroller 等包名，
        # 此时 pkg == app_package，旧逻辑会把 is_system_dialog 误判为 False，导致
        # system_dialog_visible 永远不会被置位。
        is_system_dialog = bool(pkg) and _is_system_dialog_package(pkg)
        # cache 必须对两条分支都填，否则下面 `_ancestor_clickable_cache[id(node)]`
        # 会对系统对话框节点抛 KeyError，把整个 get_screen 拖垮。
        _compute_ancestor_flags(node)
        if is_system_dialog:
            system_dialog_visible = True
        else:
            if _ancestor_has_text_cache[id(node)]:
                continue

        bounds_str = node.get("bounds", "")
        res_id = node.get("resource-id", "").split("/")[-1] if node.get("resource-id") else ""

        clickable = node.get("clickable") == "true"
        parent_clickable = not clickable and _ancestor_clickable_cache[id(node)]
        b = _parse_bounds(bounds_str)

        selected = node.get("selected") == "true"
        checked = node.get("checked") == "true"
        focused = node.get("focused") == "true"

        el = {}
        if text:
            el["text"] = text
        if desc:
            el["desc"] = desc
        if res_id:
            el["id"] = res_id
        if b:
            el["cx"] = (b[0] + b[2]) // 2
            el["cy"] = (b[1] + b[3]) // 2
        if clickable:
            el["clickable"] = True
        if parent_clickable:
            el["parent_clickable"] = True
        if selected:
            el["selected"] = True
        if checked:
            el["checked"] = True
        if focused:
            el["focused"] = True
        # P1: semantic role from widget class
        cls_short = (node.get("class") or "").rsplit(".", 1)[-1]
        role = _CLASS_ROLE_MAP.get(cls_short)
        if role:
            el["role"] = role
        elif node.get("editable") == "true" or "EditText" in (node.get("class") or ""):
            el["role"] = "input"
        elements.append(el)

    horizontal_classes = {"HorizontalScrollView", "ViewPager", "ViewPager2"}
    vertical_classes = {"ScrollView", "ListView", "GridView", "NestedScrollView"}
    recycler_classes = {"RecyclerView"}

    scrollable_areas = []
    for node in root.iter("node"):
        if node.get("scrollable") != "true" or node.get("package") == "com.android.systemui":
            continue
        cls_short = node.get("class", "").rsplit(".", 1)[-1]
        bounds_str = node.get("bounds", "")
        b = _parse_bounds(bounds_str)
        if not b:
            continue

        if cls_short in horizontal_classes:
            direction = "horizontal"
        elif cls_short in vertical_classes:
            direction = "vertical"
        elif cls_short in recycler_classes:
            children = list(node)
            if len(children) >= 2:
                b1 = _parse_bounds(children[0].get("bounds", ""))
                b2 = _parse_bounds(children[1].get("bounds", ""))
                if b1 and b2:
                    direction = "horizontal" if abs(b2[0] - b1[0]) > abs(b2[1] - b1[1]) else "vertical"
                else:
                    direction = "vertical"
            else:
                direction = "vertical"
        else:
            w, h = b[2] - b[0], b[3] - b[1]
            direction = "horizontal" if w > h * 2 else "vertical"

        res_id = node.get("resource-id", "").split("/")[-1] if node.get("resource-id") else ""
        area = {"direction": direction, "bounds": bounds_str}
        if res_id:
            area["id"] = res_id
        # 推断仍可继续滑动的方向（手指方向），让调用方直接知道是否到底
        can_swipe = _infer_can_swipe(node, direction, b, cls_short)
        area["can_swipe"] = can_swipe
        scrollable_areas.append(area)

    result = {"elements": elements, "scrollable_areas": scrollable_areas}
    if keyboard_visible:
        result["keyboard_visible"] = True
    if system_dialog_visible:
        result["system_dialog_visible"] = True
    return result


def _get_screen_sync(d: u2.Device, xml_str: Optional[str] = None) -> dict:
    """一次性获取屏幕所有信息：设备状态 + 可见元素 + 滑动区域。减少重复 RPC 调用。

    xml_str 可由调用方预先 dump 后传入（如稳态检测的最后一次 dump），避免重复抓取。
    """
    # 先获取设备信息（只调一次 app_current 和 info）
    info = d.info
    current = d.app_current()
    activity = current.get("activity", "")
    app_package = current.get("package", "")
    device_info = {
        "serial": getattr(d, "serial", None),
        "screen_on": info.get("screenOn"),
        "package": app_package,
        "activity": activity,
        "page": _build_page_path(activity),
        "display": f"{info.get('displayWidth')}x{info.get('displayHeight')}",
    }
    # 解析元素时复用 app_package；xml_str 若已提供则跳过 dump
    result = _get_visible_elements_sync(d, app_package=app_package, xml_str=xml_str)
    result["device"] = device_info
    return result


# ── 单步执行器（同步） ──


def _exec_step_sync(d: u2.Device, step: dict) -> dict:
    """执行单个步骤，返回结果 dict。"""
    action = step.get("action", "")

    if action == "tap":
        el = _select_element(d, step)
        x, y = step.get("x"), step.get("y")
        timeout = step.get("timeout", 10)
        if el is not None:
            if not el.wait(timeout=timeout):
                return {"ok": False, "reason": f"element not found: {_selector_desc(step)}"}
            # 用坐标点击，兼容 parent_clickable 元素
            info = el.info
            b = info.get("bounds", {})
            d.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
        elif x is not None and y is not None:
            d.click(x, y)
        else:
            return {"ok": False, "reason": "需要 text/textContains/desc/descContains/id/坐标"}
        return {"ok": True}

    elif action == "long_tap":
        el = _select_element(d, step)
        x, y = step.get("x"), step.get("y")
        duration = step.get("duration", 1.0)
        if el is not None:
            if not el.exists:
                return {"ok": False, "reason": f"element not found: {_selector_desc(step)}"}
            el.long_click(duration=duration)
        elif x is not None and y is not None:
            d.long_click(x, y, duration=duration)
        else:
            return {"ok": False, "reason": "需要 text/textContains/desc/descContains/id/坐标"}
        return {"ok": True}

    elif action == "input":
        # 支持指定目标元素：先点击获取焦点再输入，避免写入错误位置
        # 注意：只用 desc/descContains/id/textContains 作为目标选择器，
        # "text" 是要输入的内容，不能用作选择器
        target_keys = ("desc", "descContains", "id", "textContains")
        target_step = {k: step[k] for k in target_keys if step.get(k)}
        target = _select_element(d, target_step) if target_step else None
        if target is not None:
            if not target.exists:
                return {"ok": False, "reason": f"input target not found: {_selector_desc(target_step)}"}
            # 用坐标点击，兼容非 clickable 元素（如 Gmail 收件人字段）
            info = target.info
            b = info.get("bounds", {})
            cx = (b.get("left", 0) + b.get("right", 0)) // 2
            cy = (b.get("top", 0) + b.get("bottom", 0)) // 2
            d.click(cx, cy)
            time.sleep(0.3)

        focused = d(focused=True)
        if focused.exists:
            if step.get("clear", True):
                focused.clear_text()
            focused.set_text(step["text"])
        else:
            # fallback: 某些自定义控件（如 Gmail RecipientEditTextView）
            # focused 属性可能不为 true，直接用 send_keys 输入
            if step.get("clear", True):
                d.clear_text()
            d.send_keys(step["text"])
        return {"ok": True}

    elif action == "press":
        d.press(step["key"])
        return {"ok": True}

    elif action == "swipe":
        direction = step.get("direction", "up")
        scale = step.get("scale", 0.6)
        bounds_str = step.get("bounds")
        if bounds_str:
            d.swipe_ext(direction, box=_parse_bounds(bounds_str), scale=scale)
        else:
            d.swipe_ext(direction, scale=scale)
        return {"ok": True}

    elif action == "sleep":
        time.sleep(step.get("seconds", 1))
        return {"ok": True}

    elif action == "wait_for":
        el = _select_element(d, step)
        if el is None:
            return {"ok": False, "reason": "需要 text/desc/id 定位"}
        timeout = step.get("timeout", 10)
        exists_flag = step.get("exists", True)
        found = el.wait(timeout=timeout) if exists_flag else el.wait_gone(timeout=timeout)
        return {"ok": bool(found)}

    elif action == "app_start":
        d.app_start(step["package"], step.get("activity"))
        time.sleep(1)
        return {"ok": True}

    elif action == "app_stop":
        d.app_stop(step["package"])
        return {"ok": True}

    elif action == "get_screen":
        current = d.app_current()
        screen = _get_visible_elements_sync(d, app_package=current.get("package", ""))
        return {"ok": True, "screen": screen}

    elif action == "assert_exists":
        el = _select_element(d, step)
        if el is None:
            return {"ok": False, "abort": True, "reason": "需要 text/desc/id 定位"}
        timeout = step.get("timeout", 5)
        if not el.wait(timeout=timeout):
            return {"ok": False, "abort": True, "reason": f"'{_selector_desc(step)}' not found, aborting"}
        return {"ok": True}

    elif action == "tap_if_exists":
        el = _select_element(d, step)
        if el is None:
            return {"ok": False, "skipped": True, "reason": "需要 text/desc/id 定位"}
        timeout = step.get("timeout", 3)
        ok = el.click_exists(timeout=timeout)
        return {"ok": ok, "skipped": not ok}

    elif action == "pinch":
        # 双指缩放: "in" 缩小, "out" 放大
        pinch_action = step.get("pinch_action", "out")
        percent = step.get("percent", 80)
        bounds_str = step.get("bounds")
        if bounds_str:
            els = d.xpath(f'//*[@bounds="{bounds_str}"]').all()
            if els:
                target = els[0]
            else:
                return {"ok": False, "reason": f"bounds={bounds_str} 未找到对应元素"}
        else:
            # 全屏：选取根节点
            target = d.xpath('//*[1]').get()
        if pinch_action == "out":
            target.pinch_out(percent=percent, steps=20)
        else:
            target.pinch_in(percent=percent, steps=20)
        return {"ok": True}

    elif action == "drag":
        sx, sy = step.get("sx", 0), step.get("sy", 0)
        ex, ey = step.get("ex", 0), step.get("ey", 0)
        duration = step.get("duration", 0.5)
        d.drag(sx, sy, ex, ey, duration=duration)
        return {"ok": True}

    elif action == "scroll_to_find":
        el = _select_element(d, step)
        if el is None:
            return {"ok": False, "reason": "需要 text/desc/id 定位"}
        max_swipes = step.get("max_swipes", 10)
        direction = step.get("direction", "up")
        click = step.get("click", True)
        for i in range(max_swipes):
            if el.exists:
                if click:
                    el.click()
                return {"ok": True, "swipes": i}
            d.swipe_ext(direction, scale=0.5)
            time.sleep(0.5)
        return {"ok": False, "reason": f"'{_selector_desc(step)}' not found after {max_swipes} swipes"}

    else:
        return {"ok": False, "reason": f"unknown action '{action}'"}


def _selector_desc(step: dict) -> str:
    """生成选择器描述字符串。"""
    parts = []
    for key in ("text", "textContains", "desc", "descContains", "id"):
        if step.get(key):
            parts.append(f"{key}='{step[key]}'")
            break
    if not parts:
        return "unknown"
    idx = step.get("index", 0)
    if idx > 0:
        parts.append(f"index={idx}")
    if step.get("boundsInside"):
        parts.append(f"boundsInside={step['boundsInside']}")
    return ", ".join(parts)


# ── MCP Tools（全部 async） ──


# UI 变更类 action：执行后必须留出 settle 时间再 dump，否则会拿到旧 fragment 或
# 半渲染态。Duolingo 等带 fragment 切换/淡入动画的应用，tap 后立刻 dump 拿到的
# XML 只含外壳（toolbar + 底部按钮），中部 TextView 还没挂上 view tree。
_UI_MUTATING_ACTIONS = {
    "tap", "long_tap", "input", "press", "swipe", "drag",
    "scroll_to_find", "app_start", "app_stop", "pinch", "tap_if_exists",
}


def _dump_until_stable(d: u2.Device, max_polls: int = 3, poll_interval: float = 0.3) -> Optional[str]:
    """轮询 dump，直到两次 XML 长度一致（视为 view tree 稳定），返回最后一次 dump 的 XML。

    UI 变更后 fragment 可能仍在淡入/重排，单纯 sleep 一个固定值要么不够（动画长）
    要么浪费（动画短）。这里以"两次 dump 字节数相同"作为稳定信号 —— 节点增删
    会改变长度，文本内容变化也会改变长度，足以覆盖 fragment swap 场景。

    返回最后一次（即稳定态）的 XML，供 _get_screen_sync 复用，避免额外再 dump 一次。
    """
    try:
        prev_xml = d.dump_hierarchy(compressed=True)
    except Exception:
        return None
    for _ in range(max_polls):
        time.sleep(poll_interval)
        try:
            cur_xml = d.dump_hierarchy(compressed=True)
        except Exception:
            return prev_xml
        if len(cur_xml) == len(prev_xml):
            return cur_xml
        prev_xml = cur_xml
    return prev_xml


async def _run_action(action: str, serial: Optional[str] = None, **kwargs) -> str:
    """通用 action 执行器：构建 step dict，在线程中执行，返回 JSON。
    操作完成后自动附带返回屏幕元素，减少额外的 get_screen 调用。"""
    step = {"action": action, **{k: v for k, v in kwargs.items() if v is not None}}
    d = _get_device(serial)
    result = await asyncio.to_thread(_exec_step_sync, d, step)
    # UI 变更后等待 view tree 稳定，并复用稳定态 XML 避免额外 dump
    stable_xml: Optional[str] = None
    if action in _UI_MUTATING_ACTIONS and result.get("ok"):
        stable_xml = await asyncio.to_thread(_dump_until_stable, d)
    # 操作后自动获取屏幕，减少往返调用
    try:
        screen = await asyncio.to_thread(_get_screen_sync, d, stable_xml)
        result["screen"] = screen
    except Exception:
        pass  # 屏幕获取失败不影响操作结果
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


# -- 元素定位参数说明 --
# text/textContains/desc/descContains/id: 定位方式
# index: 多个匹配时选第N个(0-based)
# boundsInside: 限定区域"[x1,y1][x2,y2]"


@mcp.tool
async def switch_device(serial: str) -> str:
    """Switch the currently active device. After switching, all subsequent
    operations target this device by default, so the `serial` parameter no
    longer needs to be passed.

    @param serial: Device serial (e.g. "emulator-5554", "192.168.1.100:5555")
    """
    global _current_serial
    _current_serial = serial
    d = _get_device(serial)
    screen = await asyncio.to_thread(_get_screen_sync, d)
    return json.dumps({"ok": True, "message": f"Switched to device {serial}", "device": screen["device"]},
                      ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def list_devices() -> str:
    """List every currently connected Android device and mark the active one.

    Device list is obtained via `adb devices`.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run, ["adb", "devices"], capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")[1:]  # 跳过 "List of devices attached"
        devices = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                s = parts[0]
                devices.append({
                    "serial": s,
                    "status": parts[1],
                    "active": s == (_current_serial or ""),
                })
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False, separators=(",", ":"))

    return json.dumps({"ok": True, "current": _current_serial or "(auto)", "devices": devices},
                      ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def get_screen(serial: Optional[str] = None) -> str:
    """Get information about the current screen, including device state,
    visible elements, and scrollable areas.

    Returned fields:
    - device: device info (serial, current package, activity, resolution)
    - elements: list of visible elements; each entry may include
      text/desc/id/cx/cy/clickable/role and other attributes
    - scrollable_areas: scrollable regions with direction
      (horizontal/vertical) and bounds
    - keyboard_visible: whether the soft keyboard is showing

    This is the first step in interacting with the device: call it to
    understand what is on screen before deciding the next action.

    @param serial: Device serial; required when multiple devices are
        connected (e.g. "emulator-5554"). Optional with a single device.
    """
    d = _get_device(serial)
    result = await asyncio.to_thread(_get_screen_sync, d)
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def tap(text: Optional[str] = None, desc: Optional[str] = None,
              textContains: Optional[str] = None, descContains: Optional[str] = None,
              id: Optional[str] = None,
              x: Optional[int] = None, y: Optional[int] = None,
              timeout: float = 10, index: int = 0,
              boundsInside: Optional[str] = None,
              serial: Optional[str] = None) -> str:
    """Tap an element or coordinate on the screen.

    Locate the element with one of the following:
    - text: exact match on element text
    - textContains: substring match on element text
    - desc: exact match on content-description
    - descContains: substring match on content-description
    - id: matches resource-id (accepts short id like "btn_ok"
      or fully-qualified id)
    - x, y: tap a raw screen coordinate

    @param timeout: Seconds to wait for the element to appear. Default 10.
    @param index: When multiple elements match, pick the Nth one
        (0-based). Default 0.
    @param boundsInside: Restrict search to region "[x1,y1][x2,y2]";
        only elements whose center falls inside this region are matched.
    """
    return await _run_action("tap", serial=serial, text=text, desc=desc, textContains=textContains,
                             descContains=descContains, id=id, x=x, y=y,
                             timeout=timeout, index=index, boundsInside=boundsInside)


@mcp.tool
async def long_tap(text: Optional[str] = None, desc: Optional[str] = None,
                   textContains: Optional[str] = None, descContains: Optional[str] = None,
                   id: Optional[str] = None,
                   x: Optional[int] = None, y: Optional[int] = None,
                   duration: float = 1.0, index: int = 0,
                   boundsInside: Optional[str] = None,
                   serial: Optional[str] = None) -> str:
    """Long-press an element or coordinate. Commonly used to trigger
    context menus, enter drag mode, etc.

    Locator options match `tap`: text/textContains/desc/descContains/id
    or raw coordinate (x, y).

    @param duration: Long-press duration in seconds. Default 1.0.
    @param index: When multiple elements match, pick the Nth one
        (0-based). Default 0.
    @param boundsInside: Restrict search to region "[x1,y1][x2,y2]".
    """
    return await _run_action("long_tap", serial=serial, text=text, desc=desc, textContains=textContains,
                             descContains=descContains, id=id, x=x, y=y,
                             duration=duration, index=index, boundsInside=boundsInside)


@mcp.tool
async def input_text(text: str, clear: bool = True,
                     target_id: Optional[str] = None, target_desc: Optional[str] = None,
                     target_text: Optional[str] = None,
                     serial: Optional[str] = None) -> str:
    """Type text into an input field.

    If no target element is given, the text is sent to whichever field
    currently has focus. Specifying a target via the `target_*` parameters
    is preferred — this method will tap the element to acquire focus
    before typing.

    @param text: The text to type.
    @param clear: Whether to clear existing content first. Default True.
    @param target_id: resource-id of the target input field.
    @param target_desc: content-description of the target input field.
    @param target_text: substring of existing text in the target field.
    """
    return await _run_action("input", serial=serial, text=text, clear=clear,
                             id=target_id, desc=target_desc, textContains=target_text)


@mcp.tool
async def swipe(direction: str = "up", scale: float = 0.6,
                bounds: Optional[str] = None,
                serial: Optional[str] = None) -> str:
    """Swipe the screen — used for scrolling lists, paging, etc.

    @param direction: Swipe direction. One of "up" (finger up, reveals
        content below), "down", "left", "right".
    @param scale: Swipe distance in the range 0~1; higher means a longer
        swipe. Default 0.6.
    @param bounds: Restrict the swipe to region "[x1,y1][x2,y2]"; if
        omitted, swipes the full screen. Take this from the
        `scrollable_areas` returned by get_screen.
    """
    return await _run_action("swipe", serial=serial, direction=direction, scale=scale, bounds=bounds)


@mcp.tool
async def press(key: str, serial: Optional[str] = None) -> str:
    """Simulate a hardware or system key press.

    @param key: Key name. Supported values:
        - "home": go to home screen
        - "back": navigate back
        - "enter": confirm / Enter
        - "delete": backspace
        - "recent": open the recents list
        - "power": power key
        - "volume_up" / "volume_down": volume keys
        - Numeric Android KeyEvent keycodes are also accepted
          (e.g. "66" for KEYCODE_ENTER).
    """
    return await _run_action("press", serial=serial, key=key)


@mcp.tool
async def wait_for(text: Optional[str] = None, desc: Optional[str] = None,
                   textContains: Optional[str] = None, descContains: Optional[str] = None,
                   id: Optional[str] = None,
                   timeout: float = 10, exists: bool = True,
                   serial: Optional[str] = None) -> str:
    """Wait for an element to appear or disappear. Useful for page loads,
    dialog appearance, etc.

    Locators: text/textContains/desc/descContains/id (provide at least one).

    @param timeout: Maximum wait time in seconds. Default 10.
    @param exists: True waits for the element to appear (default);
        False waits for it to disappear.
    """
    return await _run_action("wait_for", serial=serial, text=text, desc=desc, textContains=textContains,
                             descContains=descContains, id=id, timeout=timeout, exists=exists)


@mcp.tool
async def app_start(package: str, activity: Optional[str] = None,
                    serial: Optional[str] = None) -> str:
    """Launch an application.

    @param package: Application package, e.g. "com.android.settings".
    @param activity: Optional Activity to launch, e.g. ".MainActivity".
        If omitted, launches the default entry.
    """
    return await _run_action("app_start", serial=serial, package=package, activity=activity)


@mcp.tool
async def app_stop(package: str, serial: Optional[str] = None) -> str:
    """Force-stop an application (equivalent to `am force-stop`).

    @param package: Application package, e.g. "com.android.settings".
    """
    return await _run_action("app_stop", serial=serial, package=package)


@mcp.tool
async def pinch(pinch_action: str = "in", percent: int = 80,
                bounds: Optional[str] = None,
                serial: Optional[str] = None) -> str:
    """Two-finger pinch gesture — used for map / image zoom and similar.

    @param pinch_action: "in" pinches the fingers together (zoom out);
        "out" spreads them apart (zoom in).
    @param percent: Pinch magnitude as a percentage; higher means a more
        pronounced zoom. Default 80.
    @param bounds: Optional region "[x1,y1][x2,y2]"; if omitted, the
        gesture is performed at the center of the screen.
    """
    return await _run_action("pinch", serial=serial, pinch_action=pinch_action, percent=percent, bounds=bounds)


@mcp.tool
async def drag(sx: int, sy: int, ex: int, ey: int, duration: float = 0.5,
               serial: Optional[str] = None) -> str:
    """Drag from a start coordinate to an end coordinate. Useful for
    progress bars, sliders, and reorderable list items.

    @param sx: Start x.
    @param sy: Start y.
    @param ex: End x.
    @param ey: End y.
    @param duration: Drag duration in seconds. Default 0.5; larger
        values produce a slower drag.
    """
    return await _run_action("drag", serial=serial, sx=sx, sy=sy, ex=ex, ey=ey, duration=duration)


@mcp.tool
async def scroll_to_find(text: Optional[str] = None, desc: Optional[str] = None,
                         textContains: Optional[str] = None, descContains: Optional[str] = None,
                         id: Optional[str] = None,
                         direction: str = "up", max_swipes: int = 10,
                         click: bool = True,
                         serial: Optional[str] = None) -> str:
    """Scroll the screen searching for an element that is not currently
    in the viewport. Useful for locating items in a long list.

    Repeatedly swipes in the given direction until the target element
    appears on screen.
    Locators: text/textContains/desc/descContains/id (provide at least one).

    @param direction: Swipe direction. Default "up" (finger up — reveals
        content below).
    @param max_swipes: Maximum number of swipes. Default 10; exceeding
        this means "not found".
    @param click: Whether to tap the element once found. Default True.
    """
    return await _run_action("scroll_to_find", serial=serial, text=text, desc=desc,
                             textContains=textContains, descContains=descContains, id=id,
                             direction=direction, max_swipes=max_swipes, click=click)


@mcp.tool
async def screenshot(serial: Optional[str] = None) -> Image:
    """Capture a screenshot of the current screen and return the JPEG
    image directly.

    Note: screenshots are expensive — prefer `get_screen` for element
    information. Use this tool only when:
    - get_screen returns very few elements but the screen clearly has
      rich content (WebView, Canvas, game scene, etc.).
    - You need to inspect visual layout or image content that the UI
      hierarchy does not expose.
    """
    d = _get_device(serial)

    def _capture() -> bytes:
        buf = io.BytesIO()
        d.screenshot().save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    return Image(data=await asyncio.to_thread(_capture), format="jpeg")


# ── WebView (H5) 支持：基于 u2_webview + DrissionPage CDP 连接 ──
#
# 适用场景：被测 App 内嵌 WebView/H5 页面，native dump 看到的是单个 WebView
# 节点或 DOM 元素稀少。前提：App 开了 setWebContentsDebuggingEnabled(true)。

_webviews: dict[str, _U2Webview] = {}


def _get_webview(serial: Optional[str] = None) -> _U2Webview:
    """获取（必要时建立）当前设备的 WebView 连接，复用同一个 browser 句柄。"""
    key = serial or _current_serial or ""
    wv = _webviews.get(key)
    if wv is None:
        wv = _U2Webview(_get_device(serial))
        wv.attach()
        _webviews[key] = wv
    return wv


# 提取 H5 页面里所有可见且可交互的元素。比把整个 DOM 喂给 LLM 更精简。
_WEBVIEW_DOM_JS = r"""
(() => {
  const out = [];
  const sel = 'a, button, input, textarea, select, [role="button"], [role="link"], [onclick], [tabindex]';
  const seen = new Set();
  document.querySelectorAll(sel).forEach((n, i) => {
    const r = n.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    if (r.bottom < 0 || r.top > window.innerHeight) return;
    const tag = n.tagName.toLowerCase();
    const text = (n.innerText || n.value || n.placeholder || '').trim().slice(0, 100);
    const id = n.id || '';
    const cls = (typeof n.className === 'string') ? n.className.trim().slice(0, 80) : '';
    const role = n.getAttribute('role') || '';
    const type = n.getAttribute('type') || '';
    const name = n.getAttribute('name') || '';
    const aria = n.getAttribute('aria-label') || '';
    const key = tag + '|' + text + '|' + id + '|' + cls + '|' + name;
    if (seen.has(key)) return;
    seen.add(key);
    const e = {tag, idx: i};
    if (text) e.text = text;
    if (id) e.id = id;
    if (cls) e.cls = cls;
    if (role) e.role = role;
    if (type) e.type = type;
    if (name) e.name = name;
    if (aria) e.aria_label = aria;
    e.cx = Math.round(r.left + r.width / 2);
    e.cy = Math.round(r.top + r.height / 2);
    out.push(e);
  });
  return {url: location.href, title: document.title, elements: out};
})()
"""


@mcp.tool
async def webview_attach(serial: Optional[str] = None) -> str:
    """Attach to the device's WebView via Chrome DevTools Protocol.

    Establishes (and caches) a CDP connection to the active WebView on the
    device. Subsequent webview_* calls reuse the same connection. The target
    App must have `setWebContentsDebuggingEnabled(true)`, otherwise no
    debuggable socket is exposed and this call fails.

    Returns the current page URL and title on success.
    """
    def _attach():
        wv = _get_webview(serial)
        page = wv.current_page
        if page is None:
            raise RuntimeError("attach succeeded but no active tab")
        return {"url": page.url, "title": page.title}
    try:
        info = await asyncio.to_thread(_attach)
        return json.dumps({"ok": True, **info}, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def webview_detach(serial: Optional[str] = None) -> str:
    """Disconnect the WebView CDP session and release the adb port forward."""
    key = serial or _current_serial or ""
    wv = _webviews.pop(key, None)
    if wv is None:
        return json.dumps({"ok": True, "message": "no active webview"},
                          ensure_ascii=False, separators=(",", ":"))
    await asyncio.to_thread(wv.detach)
    return json.dumps({"ok": True}, ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def webview_get_page(serial: Optional[str] = None) -> str:
    """Get current WebView state: URL, title, and visible interactable elements.

    Auto-attaches on first call. Returned `elements` list includes one entry
    per visible link/button/input/[role=button]/[onclick] with text/tag/id/
    class/role/aria_label and viewport-relative center (cx, cy).

    Use this as the H5-side analogue of `get_screen` — call it first to see
    what is on the page before deciding the next action.
    """
    def _get():
        wv = _get_webview(serial)
        page = wv.current_page
        if page is None:
            raise RuntimeError("no active webview tab")
        return page.run_js(_WEBVIEW_DOM_JS)
    try:
        info = await asyncio.to_thread(_get)
        return json.dumps({"ok": True, **info}, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def webview_click(selector: str, timeout: float = 10,
                        serial: Optional[str] = None) -> str:
    """Click an element inside the WebView by DrissionPage selector.

    Selector syntax (pass as-is to DrissionPage `.ele()`):
    - "text:Login"       — substring match on visible text
    - "@text=Login"      — exact text match
    - "#login-btn"       — id
    - ".btn-primary"     — class
    - "tag:button"       — tag
    - "css:button.x"     — raw CSS
    - "xpath://button[@id='x']"  — XPath
    """
    def _click():
        wv = _get_webview(serial)
        page = wv.current_page
        if page is None:
            return {"ok": False, "reason": "no active webview tab"}
        ele = page.ele(selector, timeout=timeout)
        if not ele:
            return {"ok": False, "reason": f"element not found: {selector}"}
        ele.click()
        return {"ok": True}
    try:
        return json.dumps(await asyncio.to_thread(_click),
                          ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)},
                          ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def webview_input(selector: str, text: str, clear: bool = True,
                        timeout: float = 10, serial: Optional[str] = None) -> str:
    """Type text into an H5 input/textarea by selector.

    @param selector: DrissionPage selector (see webview_click for syntax).
    @param text: Text to type.
    @param clear: Whether to clear existing content first. Default True.
    """
    def _input():
        wv = _get_webview(serial)
        page = wv.current_page
        if page is None:
            return {"ok": False, "reason": "no active webview tab"}
        ele = page.ele(selector, timeout=timeout)
        if not ele:
            return {"ok": False, "reason": f"element not found: {selector}"}
        if clear:
            ele.clear()
        ele.input(text)
        return {"ok": True}
    try:
        return json.dumps(await asyncio.to_thread(_input),
                          ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)},
                          ensure_ascii=False, separators=(",", ":"))


@mcp.tool
async def webview_eval(js: str, serial: Optional[str] = None) -> str:
    """Run JavaScript in the WebView and return its result.

    Escape hatch for anything the structured tools don't cover: scrolling
    a specific container, reading a hidden DOM attribute, dispatching a
    custom event, etc. The expression's return value is JSON-encoded if
    serializable; otherwise its string form is returned.
    """
    def _eval():
        wv = _get_webview(serial)
        page = wv.current_page
        if page is None:
            return {"ok": False, "reason": "no active webview tab"}
        return {"ok": True, "result": page.run_js(js)}
    try:
        return json.dumps(await asyncio.to_thread(_eval),
                          ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception as e:
        return json.dumps({"ok": False, "reason": str(e)},
                          ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=16165, path="/stream")
