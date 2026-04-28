"""Screen capture, OCR, and Claude Vision analysis."""
import subprocess
import os
import base64
import tempfile
from pathlib import Path


async def analyze_screen(focus: str = "full") -> str:
    """Take a screenshot and analyze it."""
    # Capture screenshot
    tmp_path = tempfile.mktemp(suffix=".png")

    if focus == "active":
        # Capture active window
        subprocess.run(["screencapture", "-x", "-w", tmp_path], timeout=5)
    else:
        # Capture full screen
        subprocess.run(["screencapture", "-x", tmp_path], timeout=5)

    if not os.path.exists(tmp_path):
        return "Screenshot capture failed. Check Screen Recording permission in System Settings."

    # Try OCR with pytesseract first
    ocr_text = ""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(tmp_path)
        ocr_text = pytesseract.image_to_string(img)
        ocr_text = ocr_text.strip()
    except Exception as e:
        ocr_text = f"OCR not available: {e}"

    # Try Claude Vision if API key is available
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic
            with open(tmp_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": "Describe what's on this screen in 2-3 sentences. Be specific and direct. Focus on what the user is doing and any notable content visible. No markdown."
                            }
                        ]
                    }
                ]
            )
            os.unlink(tmp_path)
            return response.content[0].text

        except Exception as e:
            print(f"[VISION] Claude Vision failed: {e}")

    # Clean up
    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    # Fall back to OCR text
    if ocr_text and len(ocr_text) > 20:
        return f"Screen text: {ocr_text[:1000]}"

    return "Screenshot captured but could not analyze the content. Check your API key."


def get_active_app() -> str:
    """Get the currently active application."""
    result = subprocess.run(
        ['osascript', '-e',
         'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True
    )
    return result.stdout.strip()
