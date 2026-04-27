#!/bin/bash
FILE_NAME=$1
echo "Errors made by $1"
grep "failed" -B 2 $FILE_NAME| cut -d ':' -f 5-6

