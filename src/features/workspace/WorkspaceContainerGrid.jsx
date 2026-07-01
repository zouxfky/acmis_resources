import { useState } from "react";

import { WorkspaceContainerCard } from "./WorkspaceContainerCard";

const gpuGroupCatalog = [
  { id: "gpu-1", count: 1, label: "1 卡" },
  { id: "gpu-2", count: 2, label: "2 卡" },
  { id: "gpu-4", count: 4, label: "4 卡" },
  { id: "gpu-8", count: 8, label: "8 卡" },
  { id: "gpu-0", count: 0, label: "CPU" }
];

const containerStatusSortOrder = {
  active: 0,
  disabled: 1,
  offline: 2
};


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

  const groupedContainers = gpuGroupCatalog
    .map((group) => ({
      ...group,
      containers: workspaceContainers
        .filter((container) => Number(container.gpuCount) === group.count)
        .sort((left, right) => {
          const leftStatusOrder = containerStatusSortOrder[left.status] ?? 9;
          const rightStatusOrder = containerStatusSortOrder[right.status] ?? 9;
          if (leftStatusOrder !== rightStatusOrder) {
            return leftStatusOrder - rightStatusOrder;
          }
          return Number(left.id) - Number(right.id);
        })
    }))
    .filter((group) => group.containers.length > 0);

  return (
    <section className="container-stage">
      {groupedContainers.map((group) => (
        <section className="container-group" key={group.id}>
          <div className="container-group-divider">
            <span>{group.label}</span>
          </div>
          <div className="container-grid">
            {group.containers.map((container) => (
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
      ))}
    </section>
  );
}
