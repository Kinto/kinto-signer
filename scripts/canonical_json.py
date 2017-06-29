#!/usr/bin/env python
from __future__ import print_function

import json
import sys


def main(argv):
    # Loading command args
    argv_len = len(argv)
    stdin = sys.stdin
    stdin_close = False
    stdout = sys.stdout
    stdout_close = False

    if argv_len > 1:
        stdin = open(argv[1], "r")
        stdin_close = True

    if argv_len > 2:
        stdout = open(argv[2], "w")
        stdout_close = True

    if argv_len > 3:
        print("USAGE: {} [in] [out]".format(argv[0]), file=sys.stderr)
        sys.exit(1)

    # Reading canonical_json
    records = json.load(stdin)
    json.dump(records, stdout, indent=2, sort_keys=True)

    stdout.write('\n')
    # Closing file descriptors

    if stdin_close:
        stdin.close()

    if stdout_close:
        stdout.close()


if __name__ == "__main__":
    main(sys.argv)
