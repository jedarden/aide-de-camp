#!/bin/bash
# Run extraction on all 10 sample files from the catalog

echo "=== Sample File Extraction Results ===" > sample_extraction_results.log
echo "Started at: $(date)" >> sample_extraction_results.log
echo "" >> sample_extraction_results.log

# Define the 10 sample files from the catalog
SAMPLE_FILES=(
    "logs/whisper-stt-raw.jsonl"
    "logs/pbx-web-victorialogs-raw.jsonl"
    "logs/whisper-stt-30day.jsonl"
    "logs/pbx-web-parsed.jsonl"
    "logs/pbx-web-nginx.log"
    "logs/whisper-openai-raw.log"
    "logs/pbx-web-site-generator.log"
    "logs/whisper-stt-deployment-describe.txt"
    "logs/pbx-web-pods-describe.txt"
    "logs/whisper-stt-pod-raw.log"
)

# Array to store results
declare -a RESULTS
declare -a SUCCESS
declare -a FAILED

# Process each file
for i in "${!SAMPLE_FILES[@]}"; do
    FILE="${SAMPLE_FILES[$i]}"
    FILE_NUM=$((i + 1))

    echo "Processing file $FILE_NUM/10: $FILE" | tee -a sample_extraction_results.log

    # Start timing
    START=$(date +%s.%N)

    # Run extraction
    if OUTPUT=$(.venv/bin/python extract_single_file.py "$FILE" 2>&1); then
        EXIT_CODE=0
        STATUS="SUCCESS"
    else
        EXIT_CODE=$?
        STATUS="FAILED"
    fi

    # End timing
    END=$(date +%s.%N)
    DURATION=$(echo "$END - $START" | bc)

    # Record result
    echo "" >> sample_extraction_results.log
    echo "=== File $FILE_NUM: $FILE ===" >> sample_extraction_results.log
    echo "Status: $STATUS" >> sample_extraction_results.log
    echo "Exit code: $EXIT_CODE" >> sample_extraction_results.log
    echo "Execution time: ${DURATION}s" >> sample_extraction_results.log
    echo "Output:" >> sample_extraction_results.log
    echo "$OUTPUT" >> sample_extraction_results.log
    echo "" >> sample_extraction_results.log

    # Store in array
    if [ "$EXIT_CODE" -eq 0 ]; then
        SUCCESS+=("$FILE (${DURATION}s)")
    else
        FAILED+=("$FILE (${DURATION}s) - Exit code: $EXIT_CODE")
    fi

    echo "  Status: $STATUS, Time: ${DURATION}s"
done

# Summary
echo "" >> sample_extraction_results.log
echo "=== EXTRACTION SUMMARY ===" >> sample_extraction_results.log
echo "Completed at: $(date)" >> sample_extraction_results.log
echo "" >> sample_extraction_results.log
echo "Total files processed: ${#SAMPLE_FILES[@]}" >> sample_extraction_results.log
echo "Successful extractions: ${#SUCCESS[@]}" >> sample_extraction_results.log
echo "Failed extractions: ${#FAILED[@]}" >> sample_extraction_results.log
echo "" >> sample_extraction_results.log

if [ ${#SUCCESS[@]} -gt 0 ]; then
    echo "=== Successful Files ===" >> sample_extraction_results.log
    for file in "${SUCCESS[@]}"; do
        echo "  ✓ $file" >> sample_extraction_results.log
    done
    echo "" >> sample_extraction_results.log
fi

if [ ${#FAILED[@]} -gt 0 ]; then
    echo "=== Failed Files ===" >> sample_extraction_results.log
    for file in "${FAILED[@]}"; do
        echo "  ✗ $file" >> sample_extraction_results.log
    done
fi

echo ""
echo "Extraction complete. Results saved to sample_extraction_results.log"

# Display summary
echo ""
echo "=== SUMMARY ==="
echo "Total files: ${#SAMPLE_FILES[@]}"
echo "Successful: ${#SUCCESS[@]}"
echo "Failed: ${#FAILED[@]}"

if [ ${#SUCCESS[@]} -gt 0 ]; then
    echo ""
    echo "Successful files:"
    for file in "${SUCCESS[@]}"; do
        echo "  ✓ $file"
    done
fi

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "Failed files:"
    for file in "${FAILED[@]}"; do
        echo "  ✗ $file"
    done
fi