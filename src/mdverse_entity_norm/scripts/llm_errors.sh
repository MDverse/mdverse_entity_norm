#!/bin/bash
set -o nounset
set -o errexit
set -o pipefail  

FILE_NAME=$1

CheckArgument() {
    if [[ -z "${FILE_NAME}" ]]; then
        echo "Usage: $0 <logfile>"
        exit 1
    fi
    if [[ ! -f "${FILE_NAME}" ]]; then
        echo "File not found: ${FILE_NAME}"
        exit 1
    fi
}

ExtractInput() {
    grep "failed" -B 2 "$FILE_NAME" | grep "Normalizing" | cut -d ':' -f 6
}

ExtractOutput() {
    grep "failed" -B 2 "$FILE_NAME" | grep "SimulationTime" | cut -d ':' -f 6
}

PrintNumberError() {
    paste <(ExtractInput) <(ExtractOutput) | sort | uniq -c | sort -n
}

llm_errors() {
    CheckArgument
    echo "Errors in ${FILE_NAME}:"
    PrintNumberError
}

llm_errors