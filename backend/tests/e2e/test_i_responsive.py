"""I. 响应式布局。"""
from __future__ import annotations

import pytest

from helpers import ApiMock, goto_app

pytestmark = pytest.mark.e2e

VIEWPORTS = [
    (1920, 1080),
    (1440, 900),
    (1100, 800),
    (900, 700),
    (390, 844),
]


def _open(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    api.add_doc(1, "a.md", 2)
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="chat"]')
    return api


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_horizontal_overflow(page, mock_base_url, width, height):
    page.set_viewport_size({"width": width, "height": height})
    _open(page, mock_base_url)
    page.wait_for_timeout(400)

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"{width}x{height} 出现横向溢出 {overflow}px"


@pytest.mark.parametrize("width,height,panel_visible", [
    (1920, 1080, True),
    (1440, 900, True),
    (1100, 800, False),
    (900, 700, False),
    (390, 844, False),
])
def test_panel_visibility_by_breakpoint(page, mock_base_url, width, height, panel_visible):
    page.set_viewport_size({"width": width, "height": height})
    _open(page, mock_base_url)
    page.wait_for_timeout(400)

    display = page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=\"panel\"]')).display"
    )
    assert (display != "none") is panel_visible


@pytest.mark.parametrize("width,height,drawer_visible", [
    (1920, 1080, False),
    (900, 700, False),
    (390, 844, True),
])
def test_drawer_button_only_on_mobile(page, mock_base_url, width, height, drawer_visible):
    page.set_viewport_size({"width": width, "height": height})
    _open(page, mock_base_url)
    page.wait_for_timeout(300)

    display = page.evaluate("() => getComputedStyle(document.querySelector('.drawer-btn')).display")
    assert (display != "none") is drawer_visible


def test_composer_visible_on_mobile(page, mock_base_url):
    page.set_viewport_size({"width": 390, "height": 844})
    _open(page, mock_base_url)

    assert page.locator('[data-testid="chat-input"]').is_visible()
    assert page.locator('[data-testid="chat-send"]').is_visible()


def test_mobile_drawer_opens_sidebar(page, mock_base_url):
    page.set_viewport_size({"width": 390, "height": 844})
    _open(page, mock_base_url)

    page.locator(".drawer-btn").click()
    page.wait_for_timeout(350)

    sidebar = page.locator(".sidebar")
    box = sidebar.bounding_box()
    assert box is not None and box["x"] >= 0, "抽屉打开后侧栏应进入视口"


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_dialog_fits_viewport(page, mock_base_url, width, height):
    page.set_viewport_size({"width": width, "height": height})
    _open(page, mock_base_url)

    page.evaluate("() => window.MJ.openKbForm('create', null)")
    page.wait_for_selector('[data-testid="kb-form"]')
    page.wait_for_timeout(350)  # 等入场动画（scale .99）结束再量尺寸

    box = page.locator('[data-testid="kb-form"]').bounding_box()
    assert box["x"] >= 0 and box["y"] >= 0
    assert box["x"] + box["width"] <= width + 1
    assert box["y"] + box["height"] <= height + 1
