import pytest
import numpy as np
from numpy.testing import assert_allclose, assert_equal
from iminuit import Minuit
from iminuit.cost import (
    CostSum,
    UnbinnedNLL,
    BinnedNLL,
    ExtendedUnbinnedNLL,
    ExtendedBinnedNLL,
    LeastSquares,
    NormalConstraint,
)
from collections.abc import Sequence

stats = pytest.importorskip("scipy.stats")
norm = stats.norm


def expon_cdf(x, a):
    return 1 - np.exp(-x / a)


@pytest.fixture
def unbinned():
    rng = np.random.default_rng(1)
    x = rng.normal(size=1000)
    mle = (len(x), np.mean(x), np.std(x, ddof=1))
    return mle, x


@pytest.fixture
def binned(unbinned):
    mle, x = unbinned
    nx, xe = np.histogram(x, bins=50, range=(-3, 3))
    return mle, nx, xe


@pytest.mark.parametrize("verbose", (0, 1))
def test_UnbinnedNLL(unbinned, verbose):
    mle, x = unbinned

    def pdf(x, mu, sigma):
        return norm(mu, sigma).pdf(x)

    cost = UnbinnedNLL(x, pdf, verbose=verbose)
    m = Minuit(cost, mu=0, sigma=1)
    m.limits["sigma"] = (0, None)
    m.migrad()
    assert_allclose(m.values, mle[1:], atol=1e-3)
    assert m.errors["mu"] == pytest.approx(1000 ** -0.5, rel=0.05)


@pytest.mark.parametrize("verbose", (0, 1))
def test_ExtendedUnbinnedNLL(unbinned, verbose):
    mle, x = unbinned

    def scaled_pdf(x, n, mu, sigma):
        return n, n * norm(mu, sigma).pdf(x)

    cost = ExtendedUnbinnedNLL(x, scaled_pdf, verbose=verbose)
    m = Minuit(cost, n=len(x), mu=0, sigma=1)
    m.limits["n"] = (0, None)
    m.limits["sigma"] = (0, None)
    m.migrad()
    assert_allclose(m.values, mle, atol=1e-3)
    assert m.errors["mu"] == pytest.approx(1000 ** -0.5, rel=0.05)


@pytest.mark.parametrize("verbose", (0, 1))
def test_BinnedNLL(binned, verbose):
    mle, nx, xe = binned

    def cdf(x, mu, sigma):
        return norm(mu, sigma).cdf(x)

    cost = BinnedNLL(nx, xe, cdf, verbose=verbose)
    m = Minuit(cost, mu=0, sigma=1)
    m.limits["sigma"] = (0, None)
    m.migrad()
    # binning loses information compared to unbinned case
    assert_allclose(m.values, mle[1:], rtol=0.15)
    assert m.errors["mu"] == pytest.approx(1000 ** -0.5, rel=0.05)


def test_BinnedNLL_bad_input():
    with pytest.raises(ValueError):
        BinnedNLL([1], [1], lambda x, a: 0)


@pytest.mark.parametrize("verbose", (0, 1))
def test_ExtendedBinnedNLL(binned, verbose):
    mle, nx, xe = binned

    def scaled_cdf(x, n, mu, sigma):
        return n * norm(mu, sigma).cdf(x)

    cost = ExtendedBinnedNLL(nx, xe, scaled_cdf, verbose=verbose)
    m = Minuit(cost, n=mle[0], mu=0, sigma=1)
    m.limits["n"] = (0, None)
    m.limits["sigma"] = (0, None)
    m.migrad()
    # binning loses information compared to unbinned case
    assert_allclose(m.values, mle, rtol=0.15)
    assert m.errors["mu"] == pytest.approx(1000 ** -0.5, rel=0.05)


def test_ExtendedBinnedNLL_bad_input():
    with pytest.raises(ValueError):
        ExtendedBinnedNLL([1], [1], lambda x, a: 0)


@pytest.mark.parametrize("loss", ["linear", "soft_l1", np.arctan])
@pytest.mark.parametrize("verbose", (0, 1))
def test_LeastSquares(loss, verbose):
    np.random.seed(1)
    x = np.random.rand(20)
    y = 2 * x + 1
    ye = 0.1
    y += ye * np.random.randn(len(y))

    def model(x, a, b):
        return a + b * x

    cost = LeastSquares(x, y, ye, model, loss=loss, verbose=verbose)
    m = Minuit(cost, a=0, b=0)
    m.migrad()
    assert_allclose(m.values, (1, 2), rtol=0.03)
    assert cost.loss == loss
    if loss != "linear":
        cost.loss = "linear"
        assert cost.loss != loss
    m.migrad()
    assert_allclose(m.values, (1, 2), rtol=0.02)


def test_LeastSquares_bad_input():
    with pytest.raises(ValueError):
        LeastSquares([1, 2], [1], [1], lambda x, a: 0)

    with pytest.raises(ValueError):
        LeastSquares([1, 2], [1, 2], [1], lambda x, a: 0)

    with pytest.raises(ValueError):
        LeastSquares([1], [1], [1], lambda x, a: 0, loss="foo")


def test_UnbinnedNLL_mask():
    c = UnbinnedNLL([1, np.nan, 2], lambda x, a: x + a)
    assert c.mask is None

    assert np.isnan(c(0)) == True
    c.mask = np.arange(3) != 1
    assert_equal(c.mask, (True, False, True))
    assert np.isnan(c(0)) == False


def test_UnbinnedNLL_properties():
    def pdf(x, a, b):
        return 0

    c = UnbinnedNLL([1, 2], pdf)
    assert c.pdf is pdf
    with pytest.raises(AttributeError):
        c.pdf = None
    assert_equal(c.data, [1, 2])
    c.data = [2, 3]
    assert_equal(c.data, [2, 3])
    with pytest.raises(ValueError):
        c.data = [1, 2, 3]
    assert c.verbose == 0
    c.verbose = 1
    assert c.verbose == 1


def test_ExtendedUnbinnedNLL_mask():
    c = ExtendedUnbinnedNLL([1, np.nan, 2], lambda x, a: (1, x + a))

    assert np.isnan(c(0)) == True
    c.mask = np.arange(3) != 1
    assert np.isnan(c(0)) == False


def test_ExtendedUnbinnedNLL_properties():
    def pdf(x, a, b):
        return 0

    c = ExtendedUnbinnedNLL([1, 2], pdf)
    assert c.scaled_pdf is pdf
    with pytest.raises(AttributeError):
        c.scaled_pdf = None


def test_BinnedNLL_mask():

    c = BinnedNLL([5, 1000, 1], [0, 1, 2, 3], expon_cdf)

    c_unmasked = c(1)
    c.mask = np.arange(3) != 1
    assert c(1) < c_unmasked


def test_BinnedNLL_properties():
    def cdf(x, a, b):
        return 0

    c = BinnedNLL([1], [1, 2], cdf)
    assert c.cdf is cdf
    with pytest.raises(AttributeError):
        c.cdf = None
    assert_equal(c.n, [1])
    assert_equal(c.xe, [1, 2])
    c.n = [2]
    c.xe = [2, 3]
    assert_equal(c.n, [2])
    assert_equal(c.xe, [2, 3])
    with pytest.raises(ValueError):
        c.n = [1, 2]
    with pytest.raises(ValueError):
        c.xe = [1, 2, 3]


def test_ExtendedBinnedNLL_mask():
    c = ExtendedBinnedNLL([1, 1000, 2], [0, 1, 2, 3], expon_cdf)

    c_unmasked = c(2)
    c.mask = np.arange(3) != 1
    assert c(2) < c_unmasked


def test_ExtendedBinnedNLL_properties():
    def cdf(x, a):
        return 0

    c = ExtendedBinnedNLL([1], [1, 2], cdf)
    assert c.scaled_cdf is cdf


def test_LeastSquares_mask():
    c = LeastSquares([1, 2, 3], [3, np.nan, 4], [1, 1, 1], lambda x, a: x + a)
    assert np.isnan(c(0)) == True
    c.mask = np.arange(3) != 1
    assert np.isnan(c(0)) == False


def test_LeastSquares_properties():
    def model(x, a):
        return a

    c = LeastSquares(1, 2, 3, model)
    assert_equal(c.x, [1])
    assert_equal(c.y, [2])
    assert_equal(c.yerror, [3])
    assert c.model is model
    with pytest.raises(AttributeError):
        c.model = model
    with pytest.raises(ValueError):
        c.x = [1, 2]
    with pytest.raises(ValueError):
        c.y = [1, 2]
    with pytest.raises(ValueError):
        c.yerror = [1, 2]


def test_addable_cost_1():
    def model1(x, a):
        return a + x

    def model2(x, b, a):
        return a + b * x

    def model3(x, c):
        return c

    lsq1 = LeastSquares(1, 2, 3, model1)
    assert lsq1.func_code.co_varnames == ("a",)

    lsq2 = LeastSquares(1, 3, 4, model2)
    assert lsq2.func_code.co_varnames == ("b", "a")

    lsq3 = LeastSquares(1, 1, 1, model3)
    assert lsq3.func_code.co_varnames == ("c",)

    lsq12 = lsq1 + lsq2
    assert lsq12._items == [lsq1, lsq2]
    assert isinstance(lsq12, CostSum)
    assert isinstance(lsq1, LeastSquares)
    assert isinstance(lsq2, LeastSquares)
    assert lsq12.func_code.co_varnames == ("a", "b")

    assert lsq12(1, 2) == lsq1(1) + lsq2(2, 1)

    m = Minuit(lsq12, a=0, b=0)
    m.migrad()
    assert m.parameters == ("a", "b")
    assert_allclose(m.values, (1, 2))
    assert_allclose(m.errors, (3, 5))
    assert_allclose(m.covariance, ((9, -9), (-9, 25)), atol=1e-10)

    lsq121 = lsq12 + lsq1
    assert lsq121._items == [lsq1, lsq2, lsq1]
    assert lsq121.func_code.co_varnames == ("a", "b")

    lsq312 = lsq3 + lsq12
    assert lsq312._items == [lsq3, lsq1, lsq2]
    assert lsq312.func_code.co_varnames == ("c", "a", "b")

    lsq31212 = lsq312 + lsq12
    assert lsq31212._items == [lsq3, lsq1, lsq2, lsq1, lsq2]
    assert lsq31212.func_code.co_varnames == ("c", "a", "b")

    lsq31212 += lsq1
    assert lsq31212._items == [lsq3, lsq1, lsq2, lsq1, lsq2, lsq1]
    assert lsq31212.func_code.co_varnames == ("c", "a", "b")


def test_addable_cost_2():
    ref = NormalConstraint("a", 1, 2), NormalConstraint(("b", "a"), (1, 1), (2, 2))
    cs = ref[0] + ref[1]
    assert isinstance(cs, Sequence)
    assert len(cs) == 2
    assert cs[0] is ref[0]
    assert cs[1] is ref[1]
    for c, r in zip(cs, ref):
        assert c is r
    assert cs.index(ref[0]) == 0
    assert cs.index(ref[1]) == 1
    assert cs.count(ref[0]) == 1


def test_NormalConstraint_1():
    def model(x, a):
        return a

    lsq1 = LeastSquares(0, 1, 1, model)
    lsq2 = lsq1 + NormalConstraint("a", 1, 0.1)
    assert lsq1.func_code.co_varnames == ("a",)
    assert lsq2.func_code.co_varnames == ("a",)

    m = Minuit(lsq1, 0)
    m.migrad()
    assert_allclose(m.values, (1,), atol=1e-2)
    assert_allclose(m.errors, (1,), rtol=1e-2)

    m = Minuit(lsq2, 0)
    m.migrad()
    assert_allclose(m.values, (1,), atol=1e-2)
    assert_allclose(m.errors, (0.1,), rtol=1e-2)


def test_NormalConstraint_2():
    lsq1 = NormalConstraint(("a", "b"), (1, 2), (2, 2))
    lsq2 = lsq1 + NormalConstraint("b", 2, 0.1) + NormalConstraint("a", 1, 0.01)
    sa = 0.1
    sb = 0.02
    rho = 0.5
    cov = ((sa ** 2, rho * sa * sb), (rho * sa * sb, sb ** 2))
    lsq3 = lsq1 + NormalConstraint(("a", "b"), (1, 2), cov)
    assert lsq1.func_code.co_varnames == ("a", "b")
    assert lsq2.func_code.co_varnames == ("a", "b")
    assert lsq3.func_code.co_varnames == ("a", "b")

    m = Minuit(lsq1, 0, 0)
    m.migrad()
    assert_allclose(m.values, (1, 2), atol=1e-3)
    assert_allclose(m.errors, (2, 2), rtol=1e-3)

    m = Minuit(lsq2, 0, 0)
    m.migrad()
    assert_allclose(m.values, (1, 2), atol=1e-3)
    assert_allclose(m.errors, (0.01, 0.1), rtol=1e-2)

    m = Minuit(lsq3, 0, 0)
    m.migrad()
    assert_allclose(m.values, (1, 2), atol=1e-3)
    assert_allclose(m.errors, (sa, sb), rtol=1e-2)
    assert_allclose(m.covariance, cov, rtol=1e-2)


def test_NormalConstraint_properties():
    nc = NormalConstraint(("a", "b"), (1, 2), (3, 4))
    assert_equal(nc.value, (1, 2))
    assert_equal(nc.covariance, (9, 16))
    nc.value = (2, 3)
    nc.covariance = (1, 2)
    assert_equal(nc.value, (2, 3))
    assert_equal(nc.covariance, (1, 2))
