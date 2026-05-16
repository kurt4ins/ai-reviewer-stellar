import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { clearToken, getToken } from "./api";
import Login from "./pages/Login";
import Repos from "./pages/Repos";
import Reviews from "./pages/Reviews";
import ReviewDetail from "./pages/ReviewDetail";

function Protected({ children }: { children: JSX.Element }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

function Layout({ children }: { children: JSX.Element }) {
  const navigate = useNavigate();
  return (
    <>
      <div className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          Stellar
        </div>
        <nav className="nav">
          <NavLink to="/" end>Репозитории</NavLink>
          <NavLink to="/reviews">Ревью</NavLink>
        </nav>
        <button
          className="logout-btn"
          onClick={() => { clearToken(); navigate("/login"); }}
        >
          Выйти
        </button>
      </div>
      <div className="container">{children}</div>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Layout><Repos /></Layout></Protected>} />
      <Route path="/reviews" element={<Protected><Layout><Reviews /></Layout></Protected>} />
      <Route path="/reviews/:id" element={<Protected><Layout><ReviewDetail /></Layout></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
