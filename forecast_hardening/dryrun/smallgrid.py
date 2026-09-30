"""GridSearchCV reducido para dry-run (mismo código del notebook, grilla de 1 punto y pocos árboles)."""
import sklearn.model_selection as _ms


class SmallGrid(_ms.GridSearchCV):
    def __init__(self, estimator, param_grid, **kw):
        pg = {}
        for k, v in param_grid.items():
            v = list(v)
            if k.endswith("n_estimators"):
                pg[k] = [min(v[0], 80)]
            elif k.endswith("learning_rate"):
                pg[k] = [max(v)]          # lr alto para que 80 árboles aprendan algo
            else:
                pg[k] = [v[len(v) // 2]]
        kw["n_jobs"] = 1
        kw["verbose"] = 0
        super().__init__(estimator, pg, **kw)


def install():
    _ms.GridSearchCV = SmallGrid
