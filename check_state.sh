#!/bin/bash
# Reset cwd and check tmux state
cd /home/darcy/DC/DC
echo "--- tmux sessions ---"
tmux list-sessions 2>&1
echo "--- tmux windows ---"
tmux list-windows -t DC 2>&1
echo "--- pane content ---"
tmux capture-pane -t DC -p -S -100 2>&1
echo "--- done ---"
