#! /usr/bin/env python3
from .node import TaskGenerator


def main(args: list[str] | None = None) -> None:
    del args
    TaskGenerator.run_main(aiomonitor=True)


if __name__ == '__main__':
    import time

    time.sleep(5)
    main()
