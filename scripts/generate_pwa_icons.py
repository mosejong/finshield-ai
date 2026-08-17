"""PWA 아이콘을 생성한다.

바이너리 PNG 를 소스 없이 저장소에 넣지 않기 위한 스크립트다. 색을 바꾸거나
크기를 추가할 때 이 파일만 고치고 다시 돌리면 된다.

의존성이 없다 (`zlib`, `struct` 만 쓴다). 이미지 라이브러리를 넣지 않는 이유는
P0-5 의 해시 고정 정책 때문이다 - 아이콘 4장 때문에 런타임 의존성을 늘릴 이유가
없고, 도형이 원·선분·사각형뿐이라 직접 그리는 편이 짧다.

    python scripts/generate_pwa_icons.py

색은 `web/app/globals.css` 의 토큰과 맞춘다.
  --primary  #1f3a5f  딥 네이비
  --safe     #0e7c6b  틸
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "web" / "public" / "icons"

NAVY = (0x1F, 0x3A, 0x5F)
WHITE = (0xFF, 0xFF, 0xFF)
TEAL = (0x0E, 0x7C, 0x6B)

# 가장자리 계단을 없애려고 4배로 그린 뒤 평균낸다. 도형이 단순해서 이 정도면
# 48px 로 줄여도 방패 윤곽이 뭉개지지 않는다.
SUPERSAMPLE = 4

Color = tuple[int, int, int]


def _distance_to_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _inside_rounded_rect(
    x: float, y: float, left: float, top: float, right: float, bottom: float, radius: float
) -> bool:
    if not (left <= x <= right and top <= y <= bottom):
        return False
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return math.hypot(x - cx, y - cy) <= radius


def _inside_shield(x: float, y: float, size: float, scale: float) -> bool:
    """방패 실루엣.

    위쪽은 모서리를 둥글린 사각형, 아래쪽은 타원으로 좁아지며 한 점에서 만난다.
    문장(紋章) 방패의 가장 단순한 형태고, 작은 크기에서도 무엇인지 알아볼 수 있다.
    """
    center_x = size / 2
    half_width = 0.295 * size * scale
    top = size / 2 - 0.375 * size * scale
    bottom = size / 2 + 0.375 * size * scale
    shoulder = top + 0.56 * (bottom - top)
    corner = 0.09 * size * scale

    if y < top or y > bottom:
        return False

    dx = abs(x - center_x)
    if y <= shoulder:
        if y < top + corner and dx > half_width - corner:
            return math.hypot(dx - (half_width - corner), y - (top + corner)) <= corner
        return dx <= half_width

    # 지수가 0.5 면 정확히 반타원이라 바닥이 U 자로 보인다. 조금 키워 아래쪽이
    # 뾰족하게 모이도록 한다.
    taper = (y - shoulder) / (bottom - shoulder)
    return dx <= half_width * max(0.0, 1.0 - taper * taper) ** 0.74


def _inside_check(x: float, y: float, size: float, scale: float) -> bool:
    """방패 안의 체크 표시.

    느낌표나 경고 삼각형이 아니라 체크다. 이 제품은 "확인해 준다" 이지
    "겁을 준다" 가 아니다 (docs/13 의 공포 유발 방지 규칙).
    """
    center_x = size / 2
    center_y = size / 2
    thickness = 0.055 * size * scale

    ax, ay = center_x - 0.13 * size * scale, center_y - 0.01 * size * scale
    bx, by = center_x - 0.03 * size * scale, center_y + 0.10 * size * scale
    cx, cy = center_x + 0.15 * size * scale, center_y - 0.12 * size * scale

    return (
        _distance_to_segment(x, y, ax, ay, bx, by) <= thickness
        or _distance_to_segment(x, y, bx, by, cx, cy) <= thickness
    )


def _sample(x: float, y: float, size: float, *, scale: float, rounded: bool) -> Color:
    if rounded:
        # maskable 이 아닌 아이콘은 자기 모서리를 스스로 둥글려야 한다.
        margin = 0.02 * size
        if not _inside_rounded_rect(
            x, y, margin, margin, size - margin, size - margin, 0.22 * size
        ):
            # 투명. 호출자가 알파를 붙인다.
            return (-1, -1, -1)  # type: ignore[return-value]
    if _inside_shield(x, y, size, scale):
        return TEAL if _inside_check(x, y, size, scale) else WHITE
    return NAVY


def render(size: int, *, scale: float = 1.0, rounded: bool = True) -> bytes:
    """RGBA 픽셀 바이트열을 만든다."""
    step = 1.0 / SUPERSAMPLE
    offset = step / 2
    rows: list[bytes] = []

    for py in range(size):
        row = bytearray()
        for px in range(size):
            red = green = blue = alpha = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    color = _sample(
                        px + offset + sx * step,
                        py + offset + sy * step,
                        float(size),
                        scale=scale,
                        rounded=rounded,
                    )
                    if color[0] < 0:
                        continue
                    red += color[0]
                    green += color[1]
                    blue += color[2]
                    alpha += 255
            samples = SUPERSAMPLE * SUPERSAMPLE
            covered = alpha // 255
            if covered == 0:
                row += bytes((0, 0, 0, 0))
            else:
                row += bytes(
                    (
                        red // covered,
                        green // covered,
                        blue // covered,
                        alpha // samples,
                    )
                )
        rows.append(bytes(row))

    return b"".join(b"\x00" + row for row in rows)


def write_png(path: Path, size: int, raw: bytes) -> None:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        # (파일명, 크기, 방패 배율, 모서리 둥글림)
        ("icon-192.png", 192, 1.0, True),
        ("icon-512.png", 512, 1.0, True),
        # maskable 은 OS 가 제 모양으로 잘라낸다. 잘려나가도 방패가 남도록
        # 배경을 가장자리까지 채우고 도형은 안전 영역(약 80%) 안으로 줄인다.
        ("icon-maskable-512.png", 512, 0.72, False),
        # iOS 는 자기가 모서리를 둥글리므로 정사각형 그대로 준다.
        ("apple-touch-icon.png", 180, 1.0, False),
    ]

    for name, size, scale, rounded in targets:
        write_png(OUTPUT_DIR / name, size, render(size, scale=scale, rounded=rounded))
        print(f"wrote {(OUTPUT_DIR / name).relative_to(ROOT).as_posix()} ({size}x{size})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
