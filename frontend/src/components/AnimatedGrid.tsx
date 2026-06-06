import { useCallback, useEffect, useRef, useState } from "react";

const CELL_SIZE = 40;
const FADE_DURATION = 1200;
const FLIP_DURATION = 420;

interface CellState {
  x: number;
  y: number;
  opacity: number;
  timestamp: number;
  flipTimestamp: number;
  flipProgress: number;
}

export function AnimatedGrid() {
  const gridRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number>();
  const mousePos = useRef({ x: 0, y: 0 });
  const currentCellRef = useRef({ x: -1, y: -1, timestamp: 0 });
  const [offset, setOffset] = useState(0);
  const [visible, setVisible] = useState(false);
  const [currentCell, setCurrentCell] = useState({ x: -1, y: -1, timestamp: 0 });
  const [trailCells, setTrailCells] = useState<Map<string, CellState>>(new Map());

  const calculateCell = useCallback((clientX: number, clientY: number, currentOffset: number) => {
    return {
      x: Math.floor((clientX - currentOffset) / CELL_SIZE),
      y: Math.floor((clientY - currentOffset) / CELL_SIZE),
    };
  }, []);

  const addToTrail = useCallback((x: number, y: number) => {
    const now = Date.now();
    setTrailCells((prev) => {
      const next = new Map(prev);
      next.set(`${x},${y}`, {
        x,
        y,
        opacity: 1,
        timestamp: now,
        flipTimestamp: now,
        flipProgress: 0,
      });
      return next;
    });
  }, []);

  useEffect(() => {
    currentCellRef.current = currentCell;
  }, [currentCell]);

  useEffect(() => {
    let start = performance.now();

    const animate = (time: number) => {
      const nextOffset = ((time - start) / 2000 * CELL_SIZE) % CELL_SIZE;
      setOffset(nextOffset);
      if (gridRef.current) {
        gridRef.current.style.backgroundPosition = `${nextOffset}px ${nextOffset}px`;
      }

      const now = Date.now();
      setTrailCells((prev) => {
        const next = new Map(prev);
        let changed = false;
        for (const [key, cell] of next) {
          const elapsed = now - cell.timestamp;
          const opacity = Math.max(0, 1 - elapsed / FADE_DURATION);
          const flipProgress = Math.min(1, (now - cell.flipTimestamp) / FLIP_DURATION);
          if (opacity <= 0) {
            next.delete(key);
            changed = true;
          } else if (Math.abs(opacity - cell.opacity) > 0.01 || Math.abs(flipProgress - cell.flipProgress) > 0.01) {
            next.set(key, { ...cell, opacity, flipProgress });
            changed = true;
          }
        }
        return changed ? next : prev;
      });

      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      start = 0;
    };
  }, []);

  useEffect(() => {
    const handleMove = (event: MouseEvent) => {
      mousePos.current = { x: event.clientX, y: event.clientY };
      const cell = calculateCell(event.clientX, event.clientY, offset);
      const previous = currentCellRef.current;
      if ((previous.x !== cell.x || previous.y !== cell.y) && previous.x !== -1) {
        addToTrail(previous.x, previous.y);
      }
      setCurrentCell({ ...cell, timestamp: Date.now() });
      setVisible(true);
    };

    const handleLeave = () => {
      const previous = currentCellRef.current;
      if (previous.x !== -1) addToTrail(previous.x, previous.y);
      setVisible(false);
      mousePos.current = { x: 0, y: 0 };
      setCurrentCell({ x: -1, y: -1, timestamp: 0 });
    };

    const handleOut = (event: MouseEvent) => {
      if (!event.relatedTarget) handleLeave();
    };

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseout", handleOut);
    window.addEventListener("mouseleave", handleLeave);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseout", handleOut);
      window.removeEventListener("mouseleave", handleLeave);
    };
  }, [addToTrail, calculateCell, offset]);

  const renderTile = (cell: { x: number; y: number }, opacity: number, flipProgress: number, active = false) => {
    const pop = Math.sin(Math.min(1, flipProgress) * Math.PI);
    const isDark = (cell.x + cell.y) % 3 === 0;
    const rotation = flipProgress * 180;
    const scale = 1 + (active ? 0.48 : 0.34) * pop;
    const translateZ = (active ? 26 : 18) * pop;
    const color = isDark ? "rgba(15, 86, 199, 0.92)" : "rgba(130, 204, 250, 0.86)";
    const glow = isDark ? "rgba(15, 86, 199, 0.5)" : "rgba(130, 204, 250, 0.55)";

    return (
      <div
        className="grid-tile"
        key={`${cell.x},${cell.y}${active ? "-active" : ""}`}
        style={{
          width: CELL_SIZE,
          height: CELL_SIZE,
          left: cell.x * CELL_SIZE + offset,
          top: cell.y * CELL_SIZE + offset,
          opacity,
          transform: `perspective(800px) translateZ(${translateZ}px) rotateY(${rotation}deg) scale(${scale})`,
          boxShadow: `0 ${12 * pop}px ${28 * pop}px rgba(6,59,145,${0.16 * pop}), 0 0 ${24 * pop}px ${glow}`,
        }}
      >
        <i style={{ backgroundColor: color }} />
        <b />
      </div>
    );
  };

  const proximityTiles = () => {
    if (!visible || currentCell.x === -1) return null;
    const tiles = [];
    const radius = 4;
    for (let dx = -radius; dx <= radius; dx++) {
      for (let dy = -radius; dy <= radius; dy++) {
        if (dx === 0 && dy === 0) continue;
        const cell = { x: currentCell.x + dx, y: currentCell.y + dy };
        if (trailCells.has(`${cell.x},${cell.y}`)) continue;
        const tileX = cell.x * CELL_SIZE + offset + CELL_SIZE / 2;
        const tileY = cell.y * CELL_SIZE + offset + CELL_SIZE / 2;
        const distance = Math.hypot(tileX - mousePos.current.x, tileY - mousePos.current.y);
        const maxDistance = radius * CELL_SIZE;
        if (distance > maxDistance) continue;
        const proximity = 1 - distance / maxDistance;
        tiles.push(renderTile(cell, proximity * 0.32, proximity * 0.35));
      }
    }
    return tiles;
  };

  const activeFlip = Math.min(1, (Date.now() - currentCell.timestamp) / FLIP_DURATION);

  return (
    <div className="animated-grid" aria-hidden="true">
      <div ref={gridRef} className="grid-line-layer" />
      {Array.from(trailCells.values()).map((cell) => renderTile(cell, cell.opacity * 0.68, cell.flipProgress))}
      {proximityTiles()}
      {visible && currentCell.x !== -1 ? renderTile(currentCell, 0.9, activeFlip, true) : null}
    </div>
  );
}
