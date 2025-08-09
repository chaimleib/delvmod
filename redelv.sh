#!/bin/bash

export PYTHONPATH="$(dirname $0):$PYTHONPATH"
exec redelv/redelv
