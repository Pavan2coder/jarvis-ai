// Framer Motion & CSS Transition configurations for HUD elements
export const transitionSettings = {
  default: { type: 'spring', stiffness: 300, damping: 30 },
  slow: { duration: 0.8, ease: [0.16, 1, 0.3, 1] },
};

export const hoverScaleEffect = {
  scale: 1.02,
  transition: { duration: 0.1, ease: 'easeOut' }
};

export const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08
    }
  }
};

export const itemVariants = {
  hidden: { opacity: 0, y: 15 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 260, damping: 20 }
  }
};
