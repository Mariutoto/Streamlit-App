from app_core.extractors import detect_issuer_from_sender, extract_for_sender
from app_core.pipeline import run_outlook
import pathlib
import sys
import pandas as pd

LUKB_PATH = r"C:\Users\yann.boulbenmeyer\OneDrive - Calebo Capital AG\Dokumente\Projects\Pricer Templates\LUKB\Many Ones LUKB.htm"

ENCODINGS = ["utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"]


def try_decode(path: pathlib.Path, encs=ENCODINGS):
    b = path.read_bytes()
    for e in encs:
        try:
            s = b.decode(e)
            return e, s
        except Exception:
            continue
    return None, None


def _parse_folder_arg(arg: str) -> list[str]:
    # Accept formats like "Inbox", "Inbox/Pricer", "Inbox>Pricer"
    for sep in ("/", ">", "\\"):
        if sep in arg:
            return [p for p in arg.split(sep) if p]
    return [arg]


def run_outlook_lukb(mailbox: str, folder_path: list[str], max_emails: int = 50):
    df, stats = run_outlook(mailbox, folder_path, max_emails=max_emails)
    if df is None or df.empty:
        print(f"No rows parsed from Outlook. Stats={stats}")
        return
    cand = df[df["issuer"].astype(str).str.lower().eq("lukb")]
    if cand.empty:
        print(f"Parsed rows but none for LUKB. Stats={stats}")
        print(df.head(8).to_string(index=False))
        return
    print(f"Parsed {len(cand)} LUKB rows from Outlook. Stats={stats}")
    print(cand.head(8).to_string(index=False))


def test_file(path_str: str):
    path = pathlib.Path(path_str)
    enc, html = try_decode(path)
    print(f"Decoded {path} using {enc}\n")

    if html is None:
        print("Could not decode file with tried encodings")
        return

    senders = ["lukb", "LUKB", "no-reply@lukb.ch"]
    print(f"--- Testing file: {path} ---")
    for sender in senders:
        issuer = detect_issuer_from_sender(sender)
        print(f"Sender={sender!r} -> detected issuer={issuer}")
        try:
            obj = extract_for_sender(html, sender)
        except Exception as e:
            print("  extract_for_sender raised:", repr(e))
            continue
        if obj is None:
            print("  Extract returned None")
            continue
        print("  Returned type:", type(obj))
        if isinstance(obj, pd.DataFrame):
            print(f"  DataFrame shape={obj.shape}")
            print(obj.head(4).to_string(index=False))
        elif isinstance(obj, (list, tuple)):
            print(f"  Sequence with {len(obj)} elements")
            for i, el in enumerate(obj[:3]):
                print(f"   - element {i} type={type(el)}")
                if isinstance(el, pd.DataFrame):
                    print(f"     shape={el.shape}")
                    print(el.head(3).to_string(index=False))


def main():
    # Usage:
    #   python test_lukb.py outlook "My Mailbox" "Inbox/Pricer"
    #   python test_lukb.py            # fallback to file
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "outlook":
        mailbox = sys.argv[2] if len(sys.argv) > 2 else ""
        folder = sys.argv[3] if len(sys.argv) > 3 else "Inbox"
        if not mailbox:
            print("Provide mailbox display name or SMTP as arg2.")
            return
        run_outlook_lukb(mailbox, _parse_folder_arg(folder))
    else:
        test_file(LUKB_PATH)


if __name__ == "__main__":
    main()
