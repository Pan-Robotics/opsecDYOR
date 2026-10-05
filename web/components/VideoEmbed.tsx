"use client";
import { useState } from "react";

// A YouTube embed that costs nothing until it is played: the poster frame and a
// play button are plain HTML, and the player iframe (privacy-enhanced domain, no
// cookies before play) is only created on click. Keeps the hero light on phones.
// The poster is the 1280px frame where the screen needs it and the 480px one
// elsewhere; a video without a 1280px frame falls back to the 480px one.
export default function VideoEmbed({ id, title, by }: { id: string; title: string; by?: string }) {
  const [playing, setPlaying] = useState(false);
  const watchUrl = `https://www.youtube.com/watch?v=${id}`;
  return (
    <figure className="min-w-0">
      <div className="relative aspect-video overflow-hidden rounded-xl border border-edge bg-panel">
        {playing ? (
          <iframe
            className="absolute inset-0 h-full w-full"
            src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`}
            title={title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        ) : (
          <button
            type="button"
            onClick={() => setPlaying(true)}
            aria-label={`Play video: ${title}`}
            className="group absolute inset-0 h-full w-full cursor-pointer"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`}
              srcSet={`https://i.ytimg.com/vi/${id}/hqdefault.jpg 480w, https://i.ytimg.com/vi/${id}/maxresdefault.jpg 1280w`}
              sizes="(min-width: 1024px) 420px, (min-width: 640px) 50vw, 100vw"
              onError={(e) => { if (e.currentTarget.srcset) e.currentTarget.removeAttribute("srcset"); }}
              alt=""
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover transition group-hover:scale-[1.02]"
            />
            <span aria-hidden className="absolute inset-0 bg-gradient-to-t from-bg/80 via-transparent to-transparent" />
            <span aria-hidden className="absolute left-1/2 top-1/2 grid h-14 w-14 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-brand pl-1 text-xl text-[#04101b] shadow-lg transition group-hover:bg-brand2">
              ▶
            </span>
          </button>
        )}
      </div>
      <figcaption className="mt-2 text-sm leading-snug">
        <a href={watchUrl} target="_blank" rel="noopener noreferrer" className="text-white hover:text-brand">{title}</a>
        {by && <span className="block text-xs text-muted">{by}</span>}
      </figcaption>
    </figure>
  );
}
