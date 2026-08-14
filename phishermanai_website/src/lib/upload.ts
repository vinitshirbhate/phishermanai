/**
 * POST multipart form data and report real upload progress.
 *
 * `fetch` gives no visibility into request-body progress, so the APIF forms use
 * XHR here to drive the file-upload progress bars from actual bytes sent.
 */
export function postFormDataWithProgress(
  url: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);

    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      onProgress?.(Math.round((event.loaded / event.total) * 100));
    });

    request.upload.addEventListener("load", () => onProgress?.(100));

    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100);
        resolve(request.responseText);
      } else {
        reject(new Error(request.responseText || `Request failed (${request.status}).`));
      }
    });

    request.addEventListener("error", () =>
      reject(new Error("Network error while contacting the APIF service.")),
    );
    request.addEventListener("abort", () => reject(new Error("Request aborted.")));

    request.send(form);
  });
}
