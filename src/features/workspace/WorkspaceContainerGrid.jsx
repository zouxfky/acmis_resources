import { useState } from "react";

import { WorkspaceContainerCard } from "./WorkspaceContainerCard";


export function WorkspaceContainerGrid({
  sshKeys,
  workspaceContainers,
  workspaceLoading,
  onOpenJoinDialog,
  onOpenLeaveDialog
}) {
  const [expandedProcessContainerIds, setExpandedProcessContainerIds] = useState({});

  function toggleProcessList(containerId) {
    setExpandedProcessContainerIds((current) => ({
      ...current,
      [containerId]: !current[containerId]
    }));
  }

  return (
    <section className="container-stage">
      <div className="container-grid">
        {workspaceContainers.map((container) => (
          <WorkspaceContainerCard
            key={container.id}
            container={container}
            sshKeys={sshKeys}
            workspaceLoading={workspaceLoading}
            processListExpanded={Boolean(expandedProcessContainerIds[container.id])}
            onToggleProcessList={toggleProcessList}
            onOpenJoinDialog={onOpenJoinDialog}
            onOpenLeaveDialog={onOpenLeaveDialog}
          />
        ))}
      </div>
    </section>
  );
}
