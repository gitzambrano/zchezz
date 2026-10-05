"""Human motion and stealth interaction engine based on Fitts' Law and Movement Physics.

Adapted from TikTok automation suite to Google Colab worker automation:
1. Cubic Bézier curves with natural wrist arc kinematics.
2. Movement duration calculation derived from Fitts' Law: T = a + b * log2(1 + D/W).
3. Truncated Gaussian target dispersion (avoids geometric centers).
4. Motor micro-tremors (jitter) and minimum-jerk velocity profiles.
5. Realistic human dwell time between mousedown and mouseup (70ms - 160ms).
6. Organic keep-alive mouse gliding and scrolling to avoid Colab bot detection.
"""

import math
import random
import time
from typing import Tuple, List, Optional, Any

_CURRENT_MOUSE_POS = {"x": 200.0, "y": 200.0}


def get_current_mouse_pos() -> Tuple[float, float]:
    return (_CURRENT_MOUSE_POS["x"], _CURRENT_MOUSE_POS["y"])


def set_current_mouse_pos(x: float, y: float) -> None:
    _CURRENT_MOUSE_POS["x"] = float(x)
    _CURRENT_MOUSE_POS["y"] = float(y)


def calculate_fitts_duration(distance: float, target_size: float, a: float = 0.18, b: float = 0.12) -> float:
    """Calculate target acquisition duration via Fitts' Law."""
    if target_size <= 0:
        target_size = 30.0
    if distance <= 0:
        return 0.1

    id_index = math.log2(1.0 + (distance / target_size))
    duration = a + b * id_index
    duration *= random.uniform(0.88, 1.14)
    return max(0.22, min(duration, 1.25))


def sample_target_point(box: dict) -> Tuple[float, float]:
    """Sample realistic, non-centered target coordinate within element bounding box."""
    bx = box.get("x", 0)
    by = box.get("y", 0)
    bw = max(box.get("width", 10), 10)
    bh = max(box.get("height", 10), 10)

    cx = bx + bw / 2.0
    cy = by + bh / 2.0

    sigma_x = bw * 0.15
    sigma_y = bh * 0.15

    for _ in range(10):
        gx = random.gauss(cx, sigma_x)
        gy = random.gauss(cy, sigma_y)
        if (bx + bw * 0.15) <= gx <= (bx + bw * 0.85) and (by + bh * 0.15) <= gy <= (by + bh * 0.85):
            return gx, gy

    return bx + bw * random.uniform(0.3, 0.7), by + bh * random.uniform(0.3, 0.7)


def cubic_bezier_point(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    """Calculate point on cubic Bézier curve at parameter t in [0, 1]."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return x, y


def generate_human_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    target_size: float = 30.0,
) -> List[Tuple[float, float, float]]:
    """Generate realistic mouse waypoints with smooth acceleration and tremor."""
    x0, y0 = start
    x3, y3 = end
    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy)

    if dist < 4.0:
        return [(x3, y3, 0.05)]

    total_time = calculate_fitts_duration(dist, target_size)

    if dist > 0:
        nx = -dy / dist
        ny = dx / dist
    else:
        nx, ny = 0, 1

    deviation = (dist * random.uniform(0.08, 0.22)) * (1 if random.random() < 0.5 else -1)

    p1 = (
        x0 + dx * random.uniform(0.2, 0.38) + nx * deviation * random.uniform(0.7, 1.1),
        y0 + dy * random.uniform(0.2, 0.38) + ny * deviation * random.uniform(0.7, 1.1),
    )
    p2 = (
        x0 + dx * random.uniform(0.62, 0.82) + nx * deviation * random.uniform(0.4, 0.8),
        y0 + dy * random.uniform(0.62, 0.82) + ny * deviation * random.uniform(0.4, 0.8),
    )

    num_steps = max(12, int(total_time * random.uniform(55, 75)))
    path = []

    for i in range(1, num_steps + 1):
        linear_t = i / float(num_steps)
        eased_t = linear_t * linear_t * (3.0 - 2.0 * linear_t)
        bx, by = cubic_bezier_point((x0, y0), p1, p2, (x3, y3), eased_t)

        tremor_scale = (1.0 - linear_t * 0.75) * 0.8
        bx += random.uniform(-tremor_scale, tremor_scale)
        by += random.uniform(-tremor_scale, tremor_scale)

        step_delay = (total_time / num_steps) * random.uniform(0.85, 1.15)
        path.append((bx, by, step_delay))

    path[-1] = (x3, y3, random.uniform(0.04, 0.09))
    return path


def human_move_to(page: Any, target_x: float, target_y: float, target_size: float = 35.0) -> None:
    """Move page mouse to target with natural curve and micro-jitter."""
    cur_x, cur_y = get_current_mouse_pos()
    path = generate_human_path((cur_x, cur_y), (target_x, target_y), target_size)

    for px, py, delay in path:
        page.mouse.move(px, py)
        time.sleep(delay)

    set_current_mouse_pos(target_x, target_y)


def human_click_at(page: Any, target_x: float, target_y: float, target_size: float = 35.0) -> None:
    """Execute humanized click with dwell time at coordinates."""
    human_move_to(page, target_x, target_y, target_size)
    time.sleep(random.uniform(0.06, 0.16))
    page.mouse.down()
    try:
        time.sleep(random.uniform(0.075, 0.145))
    finally:
        page.mouse.up()
    time.sleep(random.uniform(0.08, 0.22))


def human_click(page: Any, locator_or_selector: Any, timeout: float = 12000) -> None:
    """Execute 100% human-emulated click on locator or selector string."""
    if isinstance(locator_or_selector, str):
        loc = page.locator(locator_or_selector).first
    else:
        loc = locator_or_selector

    loc.wait_for(state="visible", timeout=timeout)
    loc.scroll_into_view_if_needed(timeout=timeout)
    box = loc.bounding_box()

    if not box:
        loc.click(timeout=timeout)
        return

    target_size = min(box.get("width", 30), box.get("height", 30))
    tx, ty = sample_target_point(box)
    human_click_at(page, tx, ty, target_size)


def human_type(page: Any, locator_or_selector: Any, text: str, clear_first: bool = False, timeout: float = 10000) -> None:
    """Type text into element with realistic keystroke latency."""
    if isinstance(locator_or_selector, str):
        loc = page.locator(locator_or_selector).first
    else:
        loc = locator_or_selector

    human_click(page, loc, timeout=timeout)

    if clear_first:
        page.keyboard.press("Control+A")
        time.sleep(random.uniform(0.05, 0.12))
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.08, 0.18))

    for char in text:
        page.keyboard.type(char)
        if char in ".,!?\n":
            time.sleep(random.uniform(0.05, 0.12))
        elif char == " ":
            time.sleep(random.uniform(0.02, 0.06))
        else:
            time.sleep(random.uniform(0.015, 0.045))


def human_scroll(page: Any, delta_y: int, steps: int = 6) -> None:
    """Scroll smoothly in small impulses with inertia."""
    step_delta = delta_y / steps
    for _ in range(steps):
        jitter_delta = step_delta * random.uniform(0.85, 1.15)
        page.mouse.wheel(0, jitter_delta)
        time.sleep(random.uniform(0.04, 0.09))
    time.sleep(random.uniform(0.1, 0.25))


def random_human_idle(page: Any) -> None:
    """Execute subtle human-like idle interaction to keep connection alive."""
    cur_x, cur_y = get_current_mouse_pos()
    target_x = max(100.0, min(1200.0, cur_x + random.uniform(-150.0, 150.0)))
    target_y = max(100.0, min(700.0, cur_y + random.uniform(-100.0, 100.0)))
    human_move_to(page, target_x, target_y, target_size=50.0)

    # 30% chance of small reading scroll
    if random.random() < 0.30:
        scroll_dir = random.choice([40, -40])
        human_scroll(page, scroll_dir, steps=4)
