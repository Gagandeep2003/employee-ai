import React from "react";

// Catches render-time exceptions anywhere below it in the tree. Without this,
// React unmounts the entire tree on an uncaught error and the page goes
// completely blank with nothing but a console error -- this is what was behind
// admin pages "going white": a small bug in one page (e.g. reading a field the
// API didn't return) took down the whole app instead of just that page.
//
// Used in two places: once at the very top (index.js) as a last-resort net, and
// once around each shell's <Outlet/> (keyed by route) so a crash in one page
// doesn't take the sidebar down with it -- the person can just click elsewhere.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("Unhandled error in render tree:", error, info?.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[50vh] flex items-center justify-center p-8" data-testid="error-boundary-fallback">
          <div className="max-w-md text-center">
            <h1 className="font-display text-2xl tracking-tight">Something went wrong</h1>
            <p className="text-sm text-muted-foreground mt-3">
              This page hit an unexpected error. Reloading usually fixes it — if it keeps
              happening, please let us know what you were doing right before this.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-6 px-4 py-2.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
