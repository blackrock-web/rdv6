import { useEffect, useState } from "react";
import Analysis from "./Analysis";
import NewAnalysisUI from "./NewAnalysisUI";

export default function AnalysisWrapper() {
  const [uiVersion, setUiVersion] = useState(() => localStorage.getItem("analysis_ui") || "old");

  useEffect(() => {
    const handleUiChange = () => setUiVersion(localStorage.getItem("analysis_ui") || "old");
    window.addEventListener("ui-prefs-changed", handleUiChange);
    return () => window.removeEventListener("ui-prefs-changed", handleUiChange);
  }, []);

  return uiVersion === "new" ? <NewAnalysisUI /> : <Analysis />;
}
