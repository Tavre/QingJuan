from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "assets" / "logo.png"
WINDOWS_ICON = PROJECT_ROOT / "assets" / "app_icon.ico"
ANDROID_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
WINDOWS_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def square_source(image: Image.Image) -> Image.Image:
    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    offset = ((side - image.width) // 2, (side - image.height) // 2)
    square.alpha_composite(image, offset)
    return square


def main() -> None:
    with Image.open(SOURCE) as source:
        logo = square_source(source.convert("RGBA"))

    WINDOWS_ICON.parent.mkdir(parents=True, exist_ok=True)
    logo.save(
        WINDOWS_ICON,
        format="ICO",
        sizes=[(size, size) for size in WINDOWS_SIZES],
    )

    resource_root = PROJECT_ROOT / "android" / "app" / "src" / "main" / "res"
    for directory, size in ANDROID_SIZES.items():
        output = resource_root / directory / "ic_launcher.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        resized = logo.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(output, format="PNG", optimize=True)

    print(
        "Generated Windows and Android icons from "
        f"{SOURCE.relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()
