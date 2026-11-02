import pickle
import tempfile


class PreparationCancelled(Exception):
    pass


class PreparedPlot:
    def __init__(self, motions, stop_requested):
        self.motions = motions
        self.stop_requested = stop_requested
        self.file = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")

    def prepare(self):
        self.count = 0
        batch = []
        for motion in self.motions:
            if self.stop_requested():
                raise PreparationCancelled()
            self.count += 1
            batch.append(motion)
            if len(batch) == 256:
                pickle.dump(batch, self.file, protocol=pickle.HIGHEST_PROTOCOL)
                batch.clear()
        if batch:
            pickle.dump(batch, self.file, protocol=pickle.HIGHEST_PROTOCOL)
        self.file.seek(0)

    def __iter__(self):
        while True:
            try:
                batch = pickle.load(self.file)
            except EOFError:
                return
            yield from batch

    def close(self):
        self.file.close()
