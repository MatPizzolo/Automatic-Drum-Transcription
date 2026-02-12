"use client";

import { useEffect, useRef, useCallback, useMemo } from "react";
import type { Hit, InstrumentLabel } from "@/types/api";
import { INSTRUMENT_COLORS, INSTRUMENT_LABELS } from "@/lib/constants";

const INSTRUMENT_ORDER: InstrumentLabel[] = [
  "crash",
  "ride",
  "hihat_closed",
  "hihat_open",
  "tom_high",
  "tom_mid",
  "tom_low",
  "snare",
  "kick",
];

// Pre-computed instrument index map for O(1) lookup in draw loops
const INSTRUMENT_INDEX_MAP = new Map<InstrumentLabel, number>(
  INSTRUMENT_ORDER.map((inst, i) => [inst, i])
);

const ROW_HEIGHT = 32;
const HEADER_WIDTH = 100;
const PIXELS_PER_SECOND = 80;
const DOT_MIN_RADIUS = 3;
const DOT_MAX_RADIUS = 8;
const MINIMAP_HEIGHT = 40;
const SHOW_MINIMAP_THRESHOLD = 60;

interface HitTimelineProps {
  hits: Hit[];
  durationSeconds: number;
}

export function HitTimeline({ hits, durationSeconds }: HitTimelineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const minimapCanvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Offscreen canvas for cached minimap hit layer
  const minimapHitCacheRef = useRef<HTMLCanvasElement | null>(null);
  const minimapCacheDirtyRef = useRef(true);

  const showMinimap = durationSeconds > SHOW_MINIMAP_THRESHOLD;
  const totalWidth = HEADER_WIDTH + durationSeconds * PIXELS_PER_SECOND;
  const totalHeight = INSTRUMENT_ORDER.length * ROW_HEIGHT + 20;

  // Invalidate minimap cache when hits change
  const hitsKey = useMemo(() => hits.length, [hits]);
  useEffect(() => {
    minimapCacheDirtyRef.current = true;
  }, [hitsKey]);

  const getThemeColors = useCallback(() => {
    const isDark = document.documentElement.classList.contains("dark");
    return {
      textColor: isDark ? "#a1a1aa" : "#71717a",
      gridColor: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)",
      minimapBg: isDark ? "#18181b" : "#f4f4f5",
      minimapViewport: isDark
        ? "rgba(59,130,246,0.25)"
        : "rgba(59,130,246,0.15)",
      minimapBorder: isDark
        ? "rgba(59,130,246,0.6)"
        : "rgba(59,130,246,0.5)",
    };
  }, []);

  // Virtual rendering: only draw hits within the visible viewport + buffer
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const scroll = scrollRef.current;
    if (!canvas || !scroll) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = totalWidth * dpr;
    canvas.height = totalHeight * dpr;
    canvas.style.width = `${totalWidth}px`;
    canvas.style.height = `${totalHeight}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, totalWidth, totalHeight);

    const { textColor, gridColor } = getThemeColors();

    // Viewport bounds for virtual rendering
    const vpLeft = scroll.scrollLeft;
    const vpRight = vpLeft + scroll.clientWidth;
    const bufferPx = 200;
    const renderLeft = Math.max(0, vpLeft - bufferPx);
    const renderRight = vpRight + bufferPx;

    ctx.font = "11px system-ui, sans-serif";
    ctx.textBaseline = "middle";

    INSTRUMENT_ORDER.forEach((instrument, i) => {
      const y = i * ROW_HEIGHT + ROW_HEIGHT / 2 + 10;

      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(HEADER_WIDTH, y);
      ctx.lineTo(totalWidth, y);
      ctx.stroke();

      ctx.fillStyle = textColor;
      ctx.textAlign = "right";
      ctx.fillText(INSTRUMENT_LABELS[instrument], HEADER_WIDTH - 8, y);
    });

    const interval =
      durationSeconds > 120 ? 10 : durationSeconds > 30 ? 5 : 1;
    for (let t = 0; t <= durationSeconds; t += interval) {
      const x = HEADER_WIDTH + t * PIXELS_PER_SECOND;
      if (x < renderLeft - 50 || x > renderRight + 50) continue;

      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, 10);
      ctx.lineTo(x, totalHeight);
      ctx.stroke();

      ctx.fillStyle = textColor;
      ctx.textAlign = "center";
      ctx.font = "9px system-ui, sans-serif";
      ctx.fillText(`${t}s`, x, 6);
    }

    // Draw only visible hits (virtual rendering)
    const timeLeft = Math.max(0, (renderLeft - HEADER_WIDTH) / PIXELS_PER_SECOND);
    const timeRight = (renderRight - HEADER_WIDTH) / PIXELS_PER_SECOND;

    hits.forEach((hit) => {
      if (hit.time < timeLeft || hit.time > timeRight) return;

      const rowIndex = INSTRUMENT_INDEX_MAP.get(hit.instrument);
      if (rowIndex === undefined) return;

      const x = HEADER_WIDTH + hit.time * PIXELS_PER_SECOND;
      const y = rowIndex * ROW_HEIGHT + ROW_HEIGHT / 2 + 10;
      const radius =
        DOT_MIN_RADIUS + (DOT_MAX_RADIUS - DOT_MIN_RADIUS) * hit.velocity;
      const alpha = 0.4 + 0.6 * hit.velocity;

      const color = INSTRUMENT_COLORS[hit.instrument];

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle =
        color +
        Math.round(alpha * 255)
          .toString(16)
          .padStart(2, "0");
      ctx.fill();
    });
  }, [hits, durationSeconds, totalWidth, totalHeight, getThemeColors]);

  // Build or return cached offscreen canvas with minimap hit marks
  const getMinimapHitCache = useCallback(
    (minimapWidth: number) => {
      if (!minimapCacheDirtyRef.current && minimapHitCacheRef.current) {
        return minimapHitCacheRef.current;
      }

      const offscreen = document.createElement("canvas");
      const dpr = window.devicePixelRatio || 1;
      offscreen.width = minimapWidth * dpr;
      offscreen.height = MINIMAP_HEIGHT * dpr;
      const ctx = offscreen.getContext("2d");
      if (!ctx) return null;
      ctx.scale(dpr, dpr);

      const { minimapBg } = getThemeColors();
      ctx.fillStyle = minimapBg;
      ctx.fillRect(0, 0, minimapWidth, MINIMAP_HEIGHT);

      const scale = minimapWidth / totalWidth;

      hits.forEach((hit) => {
        const rowIndex = INSTRUMENT_INDEX_MAP.get(hit.instrument);
        if (rowIndex === undefined) return;

        const x = (HEADER_WIDTH + hit.time * PIXELS_PER_SECOND) * scale;
        const y =
          (rowIndex / INSTRUMENT_ORDER.length) * (MINIMAP_HEIGHT - 4) + 2;
        const color = INSTRUMENT_COLORS[hit.instrument];

        ctx.fillStyle = color + "99";
        ctx.fillRect(x, y, 1.5, 2);
      });

      minimapHitCacheRef.current = offscreen;
      minimapCacheDirtyRef.current = false;
      return offscreen;
    },
    [hits, totalWidth, getThemeColors]
  );

  // Draw minimap: use cached hit layer, only redraw viewport indicator
  const drawMinimap = useCallback(() => {
    const canvas = minimapCanvasRef.current;
    const scroll = scrollRef.current;
    if (!canvas || !scroll || !showMinimap) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const minimapWidth = scroll.clientWidth;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = minimapWidth * dpr;
    canvas.height = MINIMAP_HEIGHT * dpr;
    canvas.style.width = `${minimapWidth}px`;
    canvas.style.height = `${MINIMAP_HEIGHT}px`;
    ctx.scale(dpr, dpr);

    // Draw cached hit layer
    const hitCache = getMinimapHitCache(minimapWidth);
    if (hitCache) {
      ctx.drawImage(hitCache, 0, 0, minimapWidth, MINIMAP_HEIGHT);
    }

    // Draw viewport indicator overlay
    const { minimapViewport, minimapBorder } = getThemeColors();
    const scale = minimapWidth / totalWidth;
    const vpX = scroll.scrollLeft * scale;
    const vpW = scroll.clientWidth * scale;

    ctx.fillStyle = minimapViewport;
    ctx.fillRect(vpX, 0, vpW, MINIMAP_HEIGHT);

    ctx.strokeStyle = minimapBorder;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(vpX, 0, vpW, MINIMAP_HEIGHT);
  }, [showMinimap, totalWidth, getThemeColors, getMinimapHitCache]);

  // Handle scroll → redraw visible hits + minimap viewport
  const handleScroll = useCallback(() => {
    requestAnimationFrame(() => {
      draw();
      drawMinimap();
    });
  }, [draw, drawMinimap]);

  // Handle minimap click → scroll to position
  const handleMinimapClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const scroll = scrollRef.current;
      const canvas = minimapCanvasRef.current;
      if (!scroll || !canvas) return;

      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const ratio = clickX / rect.width;
      const targetScroll = ratio * totalWidth - scroll.clientWidth / 2;
      scroll.scrollTo({ left: Math.max(0, targetScroll), behavior: "smooth" });
    },
    [totalWidth]
  );

  useEffect(() => {
    minimapCacheDirtyRef.current = true;
    draw();
    drawMinimap();

    const observer = new ResizeObserver(() => {
      minimapCacheDirtyRef.current = true;
      draw();
      drawMinimap();
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [draw, drawMinimap]);

  return (
    <div ref={containerRef} className="space-y-1">
      <div
        ref={scrollRef}
        className="overflow-x-auto rounded-lg border border-border"
        onScroll={handleScroll}
      >
        <canvas ref={canvasRef} className="block" />
      </div>
      {showMinimap && (
        <canvas
          ref={minimapCanvasRef}
          className="block w-full cursor-pointer rounded border border-border/50"
          style={{ height: `${MINIMAP_HEIGHT}px` }}
          onClick={handleMinimapClick}
          aria-label="Timeline minimap — click to navigate"
        />
      )}
    </div>
  );
}
