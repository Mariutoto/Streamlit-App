import os
import sys
import traceback
import webbrowser


def _log_path(base_dir: str) -> str:
    return os.path.join(base_dir, "email_pricer_log.txt")


def _notify_error(msg: str, log_file: str) -> None:
    try:
        # Try a simple Windows message box if available
        import ctypes  # type: ignore

        ctypes.windll.user32.MessageBoxW(None, f"{msg}\n\nSee log: {log_file}", "EmailPricerParser", 0x10)
    except Exception:
        # Fallback: open log in Notepad
        try:
            os.system(f'notepad "{log_file}"')
        except Exception:
            pass


def main():
    # Resolve base dir and set CWD so relative paths work
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
    os.chdir(base_dir)
    log_file = _log_path(base_dir)

    try:
        app_path = os.path.join(base_dir, "streamlit_app.py")
        if not os.path.exists(app_path):
            raise FileNotFoundError(f"streamlit_app.py not found at {app_path}")

        # First attempt: programmatic bootstrap (fastest and cleanest)
        try:
            from streamlit.web import bootstrap  # type: ignore

            flag_options = {
                "server.headless": False,
                # Let Streamlit choose a free port automatically if 8501 is blocked
                "server.port": 0,
            }
            # Open a browser proactively as well
            try:
                webbrowser.open_new_tab("http://localhost:8501")
            except Exception:
                pass
            bootstrap.run(app_path, "", [], flag_options=flag_options)
            return
        except Exception:
            # Fallback: invoke CLI entry in-process
            from streamlit.web.cli import main as st_main  # type: ignore

            sys.argv = [
                "streamlit",
                "run",
                app_path,
                "--server.headless",
                "false",
            ]
            st_main()
            return
    except Exception as e:
        # Write details to a log file and notify user
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("Failed to launch Streamlit app\n\n")
                f.write(str(e) + "\n\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        _notify_error("Failed to launch Streamlit app.", log_file)


if __name__ == "__main__":
    main()
