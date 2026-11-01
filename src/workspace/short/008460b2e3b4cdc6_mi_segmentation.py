"""Source-person-local segmentation/reconstruction for the fixed EEGNet experiment."""
import time

from mi_comparison_models import EEGNetSmall, mean_person_ba, network_logits, torch
import numpy as np


class SourceSegments:
    """Donors are exclusively the supplied fitting rows, same person and class.

    Inspired by CTNet/TCANet S&R; no author training loop or validation split
    is copied. All electrodes move together and temporal slots are preserved.
    """
    def __init__(self, labels, people, device, seed, segments=8):
        labels, people = np.asarray(labels), np.asarray(people)
        if labels.ndim != 1 or people.shape != labels.shape or set(labels) != {0, 1}:
            raise ValueError('Both classes and aligned fitting-person identities required')
        if segments != 8:
            raise ValueError('This experiment freezes eight temporal segments')
        self.boundaries = [i * 500 // segments for i in range(segments + 1)]
        groups = sorted(set(zip(people.tolist(), labels.tolist())))
        pools = [np.flatnonzero((people == person) & (labels == cls)) for person, cls in groups]
        padded = np.zeros((len(groups), max(map(len, pools))), dtype=np.int64)
        row_group = np.empty(len(labels), dtype=np.int64)
        for group, pool in enumerate(pools):
            padded[group, :len(pool)] = pool
            row_group[pool] = group
        self.pools = torch.as_tensor(padded, dtype=torch.long, device=device)
        self.lengths = torch.as_tensor([len(p) for p in pools], dtype=torch.long, device=device)
        self.row_group = torch.as_tensor(row_group, dtype=torch.long, device=device)
        self.generator = torch.Generator(device=device).manual_seed(seed + 100000)
        self.rows = len(labels)

    def reconstruct(self, fitting_x, anchors):
        if tuple(fitting_x.shape) != (self.rows, 1, 8, 500):
            raise ValueError('Only the fitting waveform tensor may supply donors')
        groups = self.row_group[anchors]
        slots = (torch.rand((len(anchors), 8), device=fitting_x.device,
                            generator=self.generator) * self.lengths[groups, None]).long()
        donors = self.pools[groups[:, None], slots]
        synthetic = torch.empty_like(fitting_x[anchors])
        for segment, (start, stop) in enumerate(zip(self.boundaries[:-1], self.boundaries[1:])):
            synthetic[..., start:stop] = fitting_x[donors[:, segment], ..., start:stop]
        return synthetic, donors


def train_augmented(train_x, train_y, train_people, validation_x, validation_y,
                    validation_people, config, seed, device, progress=None):
    """Same EEGNet/optimizer/selection as the locked baseline, one synthetic per real row."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = EEGNetSmall(config).to(device)
    labels = torch.as_tensor(train_y, dtype=torch.long, device=device)
    segments = SourceSegments(train_y, train_people, device, seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'],
                                 betas=tuple(config['betas']), weight_decay=config['weight_decay'])
    best_ba, best_epoch, best_state, history = -1.0, 0, None, []
    updates = synthetic_rows = 0
    start_time = time.monotonic()
    for epoch in range(1, config['epochs_max'] + 1):
        model.train()
        order = torch.randperm(len(train_x), device=device)
        for offset in range(0, len(order), config['batch_size']):
            selected = order[offset:offset + config['batch_size']]
            augmented, _ = segments.reconstruct(train_x, selected)
            inputs = torch.cat((train_x[selected], augmented))
            targets = labels[selected].repeat(2)
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(model(inputs), targets)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite augmentation loss; no numerical fallback')
            loss.backward()
            optimizer.step()
            model.constrain()
            updates += 1
            synthetic_rows += len(selected)
        logits = network_logits(model, validation_x)
        ba = mean_person_ba(validation_y, logits.argmax(axis=1), validation_people)
        history.append({'epoch': epoch, 'source_validation_mean_person_ba': ba})
        if ba > best_ba:
            best_ba, best_epoch = ba, epoch
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        if progress is not None and epoch % 10 == 0:
            progress(epoch, best_epoch, best_ba, time.monotonic() - start_time)
        if epoch - best_epoch >= config['early_stop_patience']:
            break
    model.load_state_dict(best_state)
    model.eval()
    return model, {'seed': seed, 'best_epoch': best_epoch, 'completed_epochs': epoch,
                   'source_validation_mean_person_ba': best_ba, 'history': history,
                   'pc_fit_seconds': time.monotonic() - start_time,
                   'parameter_count': sum(p.numel() for p in model.parameters()),
                   'optimizer_updates': updates, 'synthetic_rows_seen': synthetic_rows,
                   'real_rows_seen': len(train_x) * epoch, 'augmentation_ratio': 1,
                   'source_donor_people': sorted(np.unique(train_people).tolist())}
