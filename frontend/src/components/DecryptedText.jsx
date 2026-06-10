import React, { useState, useEffect, useRef } from 'react';

const GLYPHS = '01ABCDEFGHIJKLMNOPQRSTUVWXYZ_#$@&%X?*/\\{}[]<>+=~^';

const DecryptedText = ({
  text = '',
  speed = 40,
  maxIterations = 10,
  sequential = true,
  animateOn = 'mount', // 'mount', 'hover', 'change'
  className = '',
  style = {}
}) => {
  const [displayText, setDisplayText] = useState(text);
  const [isAnimating, setIsAnimating] = useState(false);
  const triggerRef = useRef(null);
  const currentIteration = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (animateOn === 'mount') {
      triggerAnimation();
    }
  }, []);

  useEffect(() => {
    if (animateOn === 'change') {
      triggerAnimation();
    } else {
      setDisplayText(text);
    }
  }, [text]);

  const triggerAnimation = () => {
    if (isAnimating) {
      clearInterval(timerRef.current);
    }
    setIsAnimating(true);
    currentIteration.current = 0;

    timerRef.current = setInterval(() => {
      setDisplayText(() => {
        return text
          .split('')
          .map((char, index) => {
            if (char === ' ') return ' ';

            const progress = currentIteration.current / maxIterations;
            const threshold = sequential ? progress * text.length : -1;

            if (sequential && index < threshold) {
              return text[index];
            }

            if (Math.random() < 0.25 && currentIteration.current < maxIterations) {
              return GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
            }

            if (currentIteration.current >= maxIterations) {
              return text[index];
            }

            return displayText[index] || GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
          })
          .join('');
      });

      currentIteration.current += 1;
      if (currentIteration.current > maxIterations) {
        setIsAnimating(false);
        setDisplayText(text);
        clearInterval(timerRef.current);
      }
    }, speed);
  };

  const handleMouseEnter = () => {
    if (animateOn === 'hover' && !isAnimating) {
      triggerAnimation();
    }
  };

  return (
    <span
      ref={triggerRef}
      onMouseEnter={handleMouseEnter}
      className={className}
      style={{ display: 'inline-block', fontComposite: 'none', ...style }}
    >
      {displayText}
    </span>
  );
};

export default DecryptedText;
