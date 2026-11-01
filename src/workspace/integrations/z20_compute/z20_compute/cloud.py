"""PC point-cloud fusion; transforms map each camera frame into world metres."""
import numpy as np


def rigid_transform(points, pose):
    pose = np.asarray(pose, np.float64)
    if (pose.shape != (4, 4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3], [0, 0, 0, 1])
            or not np.allclose(pose[:3, :3].T@pose[:3, :3], np.eye(3), atol=1e-5)
            or not np.isclose(np.linalg.det(pose[:3, :3]), 1, atol=1e-5)):
        raise ValueError("camera-to-world pose must be a finite rigid transform")
    points = np.asarray(points, np.float64).reshape(-1, 3)
    return points@pose[:3, :3].T+pose[:3, 3]


def fuse_clouds(clouds, poses, *, voxel_m=.005):
    if not np.isfinite(voxel_m) or voxel_m <= 0 or len(clouds) != len(poses) or not len(clouds):
        raise ValueError("one camera-to-world pose per cloud and positive voxel size required")
    points = np.concatenate([rigid_transform(cloud, pose) for cloud, pose in zip(clouds, poses)])
    points = points[np.isfinite(points).all(axis=1)]
    if not len(points):
        raise ValueError("no finite points to fuse")
    # Tolerance avoids splitting identical reprojected points at voxel boundaries.
    cells = np.floor(points/voxel_m+1e-6).astype(np.int64)
    _, inverse = np.unique(cells, axis=0, return_inverse=True)
    count = np.bincount(inverse)
    return np.stack([np.bincount(inverse, weights=points[:, i])/count for i in range(3)], axis=1)


def register_open3d(clouds, initial_poses, *, voxel_m=.005, max_distance_m=.03, min_fitness=.4):
    """Optional local ICP: slow camera motion, overlapping stationary surfaces.

    Poor registration aborts fusion; initial guesses are supplied explicitly.
    This is not global mapping or a camera pose estimator.
    """
    try:
        import open3d as o3d
    except ImportError as exc:
        raise ValueError("Open3D is required for --icp; use a compatible PC Python environment") from exc
    if len(clouds) != len(initial_poses) or not len(clouds):
        raise ValueError("one initial camera-to-world pose per cloud required")
    def cloud(points):
        value = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, np.float64)))
        return value.voxel_down_sample(voxel_m)
    poses, reports = [np.asarray(initial_poses[0], float)], []
    world = rigid_transform(clouds[0], poses[0])
    for index in range(1, len(clouds)):
        rigid_transform(clouds[index], initial_poses[index])
        registration = o3d.pipelines.registration.registration_icp(cloud(clouds[index]), cloud(world),
            max_distance_m, np.asarray(initial_poses[index], float),
            o3d.pipelines.registration.TransformationEstimationPointToPoint())
        if registration.fitness < min_fitness or registration.inlier_rmse > max_distance_m*.5:
            raise ValueError(f"view {index} has insufficient overlap or poor ICP fit")
        poses.append(registration.transformation)
        reports.append(dict(view=index, fitness=registration.fitness, rmse_m=registration.inlier_rmse))
        world = fuse_clouds(clouds[:index+1], poses, voxel_m=voxel_m)
    return poses, reports
