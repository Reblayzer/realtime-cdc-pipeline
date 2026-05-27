import { Route, Routes } from "react-router-dom";
import Storefront from "./pages/Storefront";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <Routes>
      <Route path="/"      element={<Storefront />} />
      <Route path="/admin" element={<Admin />}      />
    </Routes>
  );
}
