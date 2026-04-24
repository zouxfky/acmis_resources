import { useState } from "react";

import { WorkspaceContainerCard } from "./WorkspaceContainerCard";


export function WorkspaceContainerGrid({
  sshKeys,
  workspaceContainers,
  workspaceLoading,
  onOpenJoinDialog,
  onOpenLeaveDialog
}) {
  const [expandedContainerIds, setExpandedContainerIds] = useState({});

  function toggleContainerCard(containerId) {
    setExpandedContainerIds((current) => ({
      ...current,
      [containerId]: !current[containerId]
    }));
  }

  function setContainerCardExpanded(containerId, expanded) {
    setExpandedContainerIds((current) => ({
      ...current,
      [containerId]: expanded
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
            cardExpanded={Boolean(expandedContainerIds[container.id])}
            onToggleCardExpand={toggleContainerCard}
            onSetCardExpanded={setContainerCardExpanded}
            onOpenJoinDialog={onOpenJoinDialog}
            onOpenLeaveDialog={onOpenLeaveDialog}
          />
        ))}
      </div>
    </section>
  );
}
