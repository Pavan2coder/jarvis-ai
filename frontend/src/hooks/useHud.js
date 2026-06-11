import { useContext } from 'react';
import { HudContext } from '../store/HudContext';

export const useHud = () => {
  const context = useContext(HudContext);
  if (!context) {
    throw new Error('useHud must be used within a HudProvider');
  }
  return context;
};
