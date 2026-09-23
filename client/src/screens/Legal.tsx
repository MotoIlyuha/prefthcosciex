import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import privacy from "../legal/privacy.md?raw";
import { useBackButton } from "../lib/hooks";
import { Markdown } from "../lib/markdown";

export function LegalScreen() {
  const navigate = useNavigate();
  const back = useCallback(() => navigate(-1), [navigate]);
  useBackButton(back);
  return (
    <div className="screen legal">
      <Markdown source={privacy} />
    </div>
  );
}
