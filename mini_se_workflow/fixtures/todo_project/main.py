import json
import sys

from service import handle


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            result = {"ok": False, "error": "invalid_request"}
        else:
            result = handle(request)
    except (ValueError, TypeError):
        result = {"ok": False, "error": "invalid_request"}
    except OSError:
        result = {"ok": False, "error": "storage_error"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
