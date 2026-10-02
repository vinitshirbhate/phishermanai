import { useEffect, type RefObject } from "react";

/**
 * Calls `callback` when a pointer goes down anywhere outside `ref`.
 *
 * The ref type allows null because React 19's `useRef<T>(null)` yields
 * `RefObject<T | null>`, and the listener is registered on mousedown/touchstart
 * rather than click so a dismissal cannot be swallowed by a re-render.
 */
export const useOutsideClick = (
  ref: RefObject<HTMLElement | null>,
  callback: (event: MouseEvent | TouchEvent) => void,
) => {
  useEffect(() => {
    const listener = (event: MouseEvent | TouchEvent) => {
      // Do nothing if the click landed on the element or inside it.
      if (!ref.current || ref.current.contains(event.target as Node)) {
        return;
      }
      callback(event);
    };

    document.addEventListener("mousedown", listener);
    document.addEventListener("touchstart", listener);

    return () => {
      document.removeEventListener("mousedown", listener);
      document.removeEventListener("touchstart", listener);
    };
  }, [ref, callback]);
};
