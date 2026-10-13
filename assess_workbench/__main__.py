"""CLI must be implemented by the candidate."""
import sys

def main():
    sys.stderr.write("ERROR NOT_IMPLEMENTED\n")
    return 3

if __name__ == "__main__":
    raise SystemExit(main())
