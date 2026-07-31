import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { LearningPlanPage } from "./pages/LearningPlanPage";
import { CareerGoalPage } from "./pages/CareerGoalPage";
import { SearchPage } from "./pages/SearchPage";
import { QuizPage } from "./pages/QuizPage";

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="resources" element={<ResourcesPage />} />
            <Route path="plan" element={<LearningPlanPage />} />
            <Route path="career" element={<CareerGoalPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="quiz" element={<QuizPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
