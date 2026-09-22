from .banner import render
from .config import ROOT


def main():
    folder = ROOT / "previews"
    folder.mkdir(exist_ok=True)
    for language in ("ru", "en"):
        path = folder / f"banner-{language}.png"
        path.write_bytes(render(12, language))
        print(path)
    (folder / "banner-unicode.png").write_bytes(render(128, "ru", title="Сообщество 🎮 • LIVE 🚀"))


if __name__ == "__main__":
    main()
