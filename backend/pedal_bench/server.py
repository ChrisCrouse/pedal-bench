"""Uvicorn entry point. Imported by `python -m pedal_bench`."""

from __future__ import annotations

import webbrowser

import uvicorn

from pedal_bench import config


def main(open_browser: bool = True) -> None:
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"[pedal-bench] starting backend at {url}")
    print(f"[pedal-bench] API docs at {url}/docs")
    if open_browser:
        try:
            webbrowser.open_new_tab(url + "/docs")
        except webbrowser.Error:
            pass
    uvicorn.run(
        "pedal_bench.api.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
