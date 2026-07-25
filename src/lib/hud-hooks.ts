import { useEffect, useState } from "react";

export function useTick(intervalMs = 1000) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setN((x) => x + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return n;
}

export function useAnimatedNumber(target: number, duration = 800) {
  const [value, setValue] = useState(target);
  useEffect(() => {
    const start = value;
    const startTime = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - startTime) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(start + (target - start) * eased);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return value;
}
