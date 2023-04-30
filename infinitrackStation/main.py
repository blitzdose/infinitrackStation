import gc
import os

from baseStation import BaseStation
from loraModule.module import Module


def main():
    gc.collect()
    if "basestation" in os.listdir():
        BaseStation()
    else:
        Module()


if __name__ == "__main__":
    main()
