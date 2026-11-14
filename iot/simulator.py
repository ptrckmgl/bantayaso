"""Send a simulated CCTV event through the same multipart API as a future device.

Run from the repository root: python -m iot.simulator --device CAM-001
"""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import random
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw


def make_snapshot(dog_count: int, camera_id: str) -> bytes:
    """Generate a labeled demo frame without a camera, OpenCV, or model weights."""
    image = Image.new("RGB", (800, 450), "#99b5a7")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 180, 800, 285), fill="#657b70")
    draw.polygon([(0, 280), (800, 265), (800, 450), (0, 450)], fill="#8e9684")
    draw.line((0, 355, 800, 341), fill="#e3dbb7", width=4)
    for x in (60, 235, 495, 700):
        draw.rectangle((x, 115, x + 10, 294), fill="#3d554a")
        draw.ellipse((x - 30, 72, x + 40, 157), fill="#547765")
    for n in range(dog_count):
        x = 145 + n * 160
        y = 295 + n % 2 * 25
        draw.ellipse((x, y, x + 91, y + 59), fill="#d8b38b")
        draw.ellipse((x - 25, y + 8, x + 20, y + 49), fill="#d8b38b")
        draw.polygon([(x - 18, y + 15), (x - 25, y - 13), (x + 1, y + 7)], fill="#bf9777")
        for leg_x in (x + 16, x + 74):
            draw.rectangle((leg_x, y + 47, leg_x + 11, y + 77), fill="#c6a17d")
        draw.arc((x + 76, y - 6, x + 132, y + 55), 180, 330, fill="#d8b38b", width=9)
    draw.rounded_rectangle((18, 18, 227, 51), 6, fill="#21382e")
    draw.text((30, 28), f"SIMULATED CCTV  |  {camera_id}", fill="white")
    draw.text((20, 425), "DEMO FRAME  •  NO LIVE CAMERA", fill="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def multipart(fields: dict[str, str], image: bytes):
    boundary = f"----straywatch{uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"snapshot\"; filename=\"demo.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
    body.extend(image)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def send_detection(api_url: str, device_id: str, dog_count: int):
    fields = {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dog_count": str(dog_count),
        "confidence": str(round(random.uniform(.84, .98), 2)),
        "source": "simulator",
    }
    body, content_type = multipart(fields, make_snapshot(dog_count, device_id))
    request = Request(f"{api_url.rstrip('/')}/api/detections", data=body,
                      headers={"Content-Type": content_type}, method="POST")
    with urlopen(request, timeout=15) as response:
        return json.load(response)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send simulated dog detection to StrayWatch API")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--device", default="CAM-001")
    parser.add_argument("--dogs", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    event = send_detection(args.api, args.device, args.dogs)
    print(f"Sent {event['id']}: {event['dog_count']} dogs at {event['location']['name']}")
