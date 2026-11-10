import { Link, Outlet } from "react-router-dom";

export function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/">
          <h1>Code Snippet Reviewer</h1>
        </Link>
        <span className="sub">AI-assisted review for ad-hoc code snippets</span>
      </header>
      <Outlet />
    </>
  );
}
