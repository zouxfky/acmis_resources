export const emptyAdminUserForm = {
  id: null,
  username: "",
  real_name: "",
  password: "",
  role: "user",
  new_password: "",
  max_ssh_keys_per_user: "",
  max_join_keys_per_request: "",
  max_containers_per_user: ""
};

export function createEmptyAdminContainerPortMappings() {
  return Array.from({ length: 3 }, (_, index) => ({
    slot_index: index + 1,
    public_port: "",
    container_port: ""
  }));
}

export function createEmptyAdminContainerForm() {
  return {
    id: null,
    name: "",
    host: "",
    ssh_port: "",
    root_password: "",
    max_users: "",
    status: "",
    port_mappings: createEmptyAdminContainerPortMappings()
  };
}

export const adminSectionCatalog = [
  { id: "users", label: "用户管理" },
  { id: "containers", label: "服务器管理" }
];
