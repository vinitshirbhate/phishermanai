"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/** A looping, autoplaying video pinned to a fixed playback rate — HTML video has no declarative speed attribute. */
export function SpeedVideo({
  src,
  rate = 1.5,
  className,
}: {
  src: string;
  rate?: number;
  className?: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;

    const applyRate = () => {
      if (video.playbackRate !== rate) video.playbackRate = rate;
    };

    applyRate();
    // Chrome/Safari can quietly reset playbackRate to 1 on the loop
    // restart — reassert it on every signal that touches the current time.
    video.addEventListener("loadedmetadata", applyRate);
    video.addEventListener("ratechange", applyRate);
    video.addEventListener("seeked", applyRate);
    video.addEventListener("play", applyRate);

    // Autoplay can be silently rejected before hydration settles — retry once.
    video.play().catch(() => {});

    return () => {
      video.removeEventListener("loadedmetadata", applyRate);
      video.removeEventListener("ratechange", applyRate);
      video.removeEventListener("seeked", applyRate);
      video.removeEventListener("play", applyRate);
    };
  }, [rate]);

  return (
    <video
      ref={ref}
      src={src}
      autoPlay
      loop
      muted
      playsInline
      preload="auto"
      disablePictureInPicture
      disableRemotePlayback
      className={cn("block w-full [transform:translateZ(0)]", className)}
    />
  );
}
