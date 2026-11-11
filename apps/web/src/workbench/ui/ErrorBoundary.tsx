import { Component, type ReactNode } from "react";

/** Shows `fallback` in place of a subtree that threw. With no boundary above it, React unmounts the whole app. */
export class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  override render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
