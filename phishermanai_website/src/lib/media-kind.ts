/**
 * Client-side mirror of the backend's `_kind_for` in apif/api/analyze.py.
 *
 * The forms need to predict which pipeline the server will route an upload
 * through, so the loader can narrate the stages that will actually run. Keep the
 * suffix sets and the precedence rule in step with that function — extension is
 * authoritative when present, MIME type is the fallback.
 */

export type MediaKind = "audio" | "video" | "image";

const AUDIO_SUFFIXES = [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"];
const VIDEO_SUFFIXES = [".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"];
const IMAGE_SUFFIXES = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"];

/** Every extension the backend accepts, for an `accept` attribute. */
export const ACCEPTED_MEDIA = [
  ...AUDIO_SUFFIXES,
  ...VIDEO_SUFFIXES,
  ...IMAGE_SUFFIXES,
].join(",");

/**
 * Returns the pipeline the backend will route this file to, or null when the
 * type is one it would reject with a 415.
 */
export function kindForFile(file: File | null): MediaKind | null {
  if (!file) return null;

  const dot = file.name.lastIndexOf(".");
  const suffix = dot === -1 ? "" : file.name.slice(dot).toLowerCase();

  if (AUDIO_SUFFIXES.includes(suffix)) return "audio";
  if (VIDEO_SUFFIXES.includes(suffix)) return "video";
  if (IMAGE_SUFFIXES.includes(suffix)) return "image";

  const mime = (file.type || "").toLowerCase();
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("image/")) return "image";

  return null;
}
