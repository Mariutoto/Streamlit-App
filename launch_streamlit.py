import os
import sys


def main():
    try:
        # Resolve the app path next to the executable (frozen) or this file
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
        app_path = os.path.join(base_dir, "streamlit_app.py")

        # Prefer Streamlit's programmatic bootstrap to avoid shelling out
        from streamlit.web import bootstrap  # type: ignore

        # Run Streamlit app in-process. Let Streamlit pick the default port (8501)
        flag_options = {
            # Ensure a browser opens on launch for user convenience
            "server.headless": False,
        }
        bootstrap.run(app_path, "", [], flag_options=flag_options)
    except Exception as e:
        # Last-resort: print an error to console if something goes wrong
        # In --noconsole builds this won't be visible, but helpful for console runs
        print(f"Failed to launch Streamlit app: {e}")


if __name__ == "__main__":
    main()

