from .permissions import can_create_appointments, is_technician, is_technician_workspace


def workspace(request):
    namespace = "backoffice" if getattr(request.resolver_match, "namespace", "") == "backoffice" else "appointments"
    navigation = {
        "can_create_appointments": can_create_appointments(request.user),
        "workspace_base": "backoffice/base.html" if namespace == "backoffice" else "base.html",
        "in_backoffice": namespace == "backoffice",
        "workflow_urls": {name: f"{namespace}:{name}" for name in ("list", "create", "update", "detail", "cancel", "status_update", "intervention_update", "availability", "documents", "pdf", "message")},
    }
    if not request.user.is_authenticated:
        return {"is_technician": False, "technician_workspace": False, "client_features": False, "workspace_home": "maintenance:pc_list", **navigation}
    technician = is_technician_workspace(request.user)
    return {"is_technician": is_technician(request.user), "technician_workspace": technician, "client_features": not technician, "workspace_home": "appointments:list" if technician else "maintenance:pc_list", **navigation}
