import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

/** Match Bootstrap lg breakpoint — same as `d-lg-none` menu in Topbar */
const MOBILE_BREAKPOINT = "(max-width: 991.98px)";

// ── State ──

interface UIState {
  sidebarCollapsed: boolean;
  sidebarMobileOpen: boolean;
}

// ── Actions ──

type UIAction =
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_SIDEBAR_MOBILE"; payload: boolean };

// ── Reducer ──

function uiReducer(state: UIState, action: UIAction): UIState {
  switch (action.type) {
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed };
    case "SET_SIDEBAR_MOBILE":
      return { ...state, sidebarMobileOpen: action.payload };
    default:
      return state;
  }
}

// ── Context Type ──

interface UIContextValue extends UIState {
  /** Viewport ≤991px: sidebar is an off-canvas drawer, not the desktop rail */
  isMobile: boolean;
  toggleSidebar: () => void;
  setSidebarMobileOpen: (open: boolean) => void;
}

const UIContext = createContext<UIContextValue | undefined>(undefined);

// ── Provider ──

export function UIProvider({ children }: { children: ReactNode }) {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(MOBILE_BREAKPOINT).matches : false
  );

  const [state, dispatch] = useReducer(uiReducer, {
    sidebarCollapsed: false,
    sidebarMobileOpen: false,
  });

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_BREAKPOINT);
    const onChange = () => {
      const mobile = mq.matches;
      setIsMobile(mobile);
      if (!mobile) {
        dispatch({ type: "SET_SIDEBAR_MOBILE", payload: false });
      }
    };
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggleSidebar = useCallback(() => {
    dispatch({ type: "TOGGLE_SIDEBAR" });
  }, []);

  const setSidebarMobileOpen = useCallback((open: boolean) => {
    dispatch({ type: "SET_SIDEBAR_MOBILE", payload: open });
  }, []);

  return (
    <UIContext.Provider
      value={{ ...state, isMobile, toggleSidebar, setSidebarMobileOpen }}
    >
      {children}
    </UIContext.Provider>
  );
}

// ── Hook ──

export function useUI(): UIContextValue {
  const context = useContext(UIContext);
  if (!context) {
    throw new Error("useUI must be used within a UIProvider");
  }
  return context;
}
