"""Private media_player.py entry for the existing session and recovery protocol."""
import sys

from historical_entry import main


if __name__ == '__main__':
    main(['player', *sys.argv[1:]])
