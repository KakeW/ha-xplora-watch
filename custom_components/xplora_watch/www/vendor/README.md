benz-amr-recorder 1.1.5, MIT license, from
https://registry.npmjs.org/benz-amr-recorder/-/benz-amr-recorder-1.1.5.tgz
(https://github.com/BenzLeung/benz-amr-recorder).

The distributed readable BenzAMRRecorder.js is vendored locally; no CDN is used.
Both occurrences of `AMR.encode(samples, sampleRate, 7)` are changed to mode 0
(4.75 kbit/s), keeping a 15-second AMR-NB recording below Xplora's documented
11.2 KB voice-message limit. The adjacent LICENSE is retained verbatim.

`rawAMRData2Blob` uses the Uint8Array view itself, rather than its backing
ArrayBuffer. The encoder returns a subarray, and including the unused tail
would append incomplete AMR frames to recordings of fractional-second length.
Indentation and trailing whitespace are normalized for repository checks.
