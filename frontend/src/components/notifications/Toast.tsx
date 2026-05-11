// src/components/notifications/Toast.tsx
import { useEffect, useState } from 'react';

interface ToastProps {
    message: string;
    duration?: number;      // 毫秒，默认 5000
    onClose?: () => void;
}

export default function Toast({ message, duration = 5000, onClose }: ToastProps) {
    const [visible, setVisible] = useState(true);

    useEffect(() => {
        const timer = setTimeout(() => {
            setVisible(false);
            onClose?.();
        }, duration);
        return () => clearTimeout(timer);
    }, [duration, onClose]);

    if (!visible) return null;

    return (
        <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-right-5 fade-in duration-300">
            <div className="bg-white rounded-lg shadow-xl border border-gray-200 w-80 p-4 relative">
                <button
                    onClick={() => {
                        setVisible(false);
                        onClose?.();
                    }}
                    className="absolute top-2 right-2 text-gray-400 hover:text-gray-600 transition"
                >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M11.3333 1.16667L10.1667 0L5.33333 4.83333L0.5 0L-0.666667 1.16667L4.16667 6L-0.666667 10.8333L0.5 12L5.33333 7.16667L10.1667 12L11.3333 10.8333L6.5 6L11.3333 1.16667Z" fill="currentColor"/>
                    </svg>
                </button>
                <p className="text-sm text-gray-700 pr-4">{message}</p>
            </div>
        </div>
    );
}
