import numpy
from pylearn2.utils.iteration import resolve_iterator_class
import Image

hack = False


class EmotiwArrangerIter(object):
    """
    Iterator for the data arranger class
    """
    _default_seed = (17, 2, 946)

    def __init__(self,
                 inst,
                 iter_mode=None,
                 batch_size=None,
                 topo=None,
                 targets=True,
                 rng=_default_seed):

        self.num_selected = [0]*len(inst.datasets)
        
        self.inst = inst
        self.img_per_seq = self.inst.img_per_seq
        self.n_face_per_batch = [round(batch_size * self.inst.weights[i]) for i in xrange(len(self.inst.weights))]
        self.batch_size = batch_size

        self.rng = numpy.random.RandomState(rng)

        self.total_n_exs = self.inst.total_n_exs
        self.topo = topo
        self.targets = targets
        self.iter_mode = iter_mode

        self.img_idx = [0]*len(self.inst.datasets)

    @staticmethod
    def fisher_yates_shuffle(imgs, tgts):
        length = imgs.shape[0]
        for i in xrange(length):
            j = numpy.random.randint(0, length)
            imgs[i], imgs[j] = imgs[j], imgs[i]
            tgts[i], tgts[j] = tgts[j], tgts[i]
        return imgs, tgts

    @staticmethod
    def _mix_faces(imgs, tgts):
        #TODO: verify correctness. The original shuffled tgts and returned
        #face_tgts.
        face_imgs = numpy.concatenate(tuple(imgs))
        face_tgts = numpy.concatenate(tuple(tgts))
        EmotiwArrangerIter.fisher_yates_shuffle(face_imgs, face_tgts)
        return face_imgs, face_tgts

    def _pick_idx_given_rnd(self, rnd, weights, num_left):
        cumul_sum = [sum(weights[0:i+1]) * int(num_left[i] != 0) for i in xrange(len(weights))]
        #0 if none left, cumulative sum otherwise.

        #return the index if:
        # - the cumulative sum is larger than rnd (we search from left to
        # right)
        # - all the remaining elements are 0
        #
        # In other words, if all the elements from a given set
        # have been selected for this batch, do as if it didn't exist.
        # If this is the last non-0 elements (left), then this is the one we
        # should sample from.
        for idx, x in enumerate(cumul_sum):
            if x > rnd or (idx < len(cumul_sum)-1 and sum(cumul_sum[idx+1:])==0):
                return idx

    def _get_sequence_idx(self, dset, elem_idx):
        len_lst = [max(1, len(dset.get_sequence(seq))- (self.img_per_seq-1)) for seq in xrange(len(dset))]
        cumul_sum = [0]*len(len_lst)
        for idx, l in enumerate(len_lst):
            if idx == 0:
                cumul_sum[0] = l
            else:
                cumul_sum[idx] = cumul_sum[idx-1] + l

        for idx, tsum in enumerate(cumul_sum):
            if tsum > elem_idx:
                s = 0
                if idx != 0:
                    s = cumul_sum[idx - 1]
                return (idx, s)

    def next(self):
        images, targets = [], []
        next_index = self.iter_mode.next()
        batch_idx = [0]*len(self.inst.datasets)

        die_values = self.rng.rand(self.batch_size)

        for i in xrange(next_index.start, next_index.stop):
            die_value = die_values[sum(batch_idx)]
            pick_from = self._pick_idx_given_rnd(die_value, self.inst.weights,
                    numpy.asarray(self.n_face_per_batch) - numpy.asarray(batch_idx))
            batch_idx[pick_from] += 1
            self.img_idx[pick_from] += 1
            self.num_selected[pick_from] += 1
            print i
            dset = self.inst.datasets[pick_from]
            elem_idx = self.img_idx[pick_from] % len(dset)
            #if the weights are set such that we want more of a given
            #dset than is available, the index will wrap around
            #for the given dset to continue picking data from it.

            the_vals = None

            if hasattr(dset, 'get_sequence'):
                seq_idx, prev_sum = self._get_sequence_idx(dset, elem_idx)
                img_idx = elem_idx - prev_sum
                sequence = dset.get_sequence(seq_idx)
                missing_frames =  self.img_per_seq - (len(sequence)-img_idx)
                the_img = []

                if missing_frames > 0:
                    for i in xrange(img_idx, len(sequence)):
                        the_img.append(sequence.get_original_image(i))
                    for i in xrange(missing_frames):
                        the_img.append(the_img[-1])

                else:
                    offset = (self.img_per_seq-1)/2
                    img_this_seq = range(max(0, img_idx-offset), max(len(sequence), img_idx+offset+1))
                    the_img = [sequence.get_original_image(i)
                               for i in img_this_seq]

                the_vals = (the_img, [sequence.get_7emotion_index(0)]*self.img_per_seq)

            else:
                the_vals = ([sequence.get_original_image(elem_idx)]*self.img_per_seq, [sequence.get_7emotion_index(0)]*self.img_per_seq)

            if hack:
                the_vals = ([numpy.fromstring(Image.frombuffer(data=x, size=(1024, 576), mode='RGB').resize((48, 48)).tostring(), dtype=numpy.uint8) for x in the_vals[0]], the_vals[1])

            images.append(the_vals[0])
            targets.append(the_vals[1])

        images = numpy.asarray(images)
        targets = numpy.asarray(targets)
        return images, targets

    def __iter__(self):
        return self


class ArrangementGenerator(object):
    """
    This generator takes N dataset objects, and combines them offline. Expects get_original_image to return an ndarray-type object
    """
    def __init__(self,
                 datasets,
                 weights,
                 size=(48,48),
                 img_per_seq = 3,
                 n_chan=1):

        assert len(weights) == len(datasets)

        self.datasets = datasets
        total_weight = float(sum(weights))
        self.weights = [float(w)/total_weight for w in weights]
        self.ex_per_dset = []
        self.total_n_exs = 0
        assert img_per_seq%2 == 1, 'img_per_seq must be odd'
        self.img_per_seq = img_per_seq

        for dset in datasets:
            if hasattr(dset, 'get_sequence'):
                self.ex_per_dset.append(0)
                for seq in xrange(len(dset)):
                    self.ex_per_dset[-1] += max(1, len(dset.get_sequence(seq)) - (self.img_per_seq-1))
                    # images grouped by 3 frames, with overlap. [XOOOOOX] is the range
                    # of valid positions that can yield a frame for times t, t-1 and t+1.
                    # Should there be less than 3 frames available, missing frames will
                    # be generated by copying the last available frame.
            else:
                self.ex_per_dset.append(len(dset))

        self.total_n_exs = sum(self.ex_per_dset)
        self.img_res = size
        self.num_channels = n_chan

    def iterator(self,
                 mode='sequential',
                 batch_size=None,
                 num_batches=None,
                 rng=None):
        """
        Method inherited from the Dataset.
        """
        if batch_size is None and mode == 'sequential':
            batch_size = 100 #Has to be big enough or we'll never pick anything.

        self.batch_size = batch_size
        self.mode = resolve_iterator_class(mode)

        self.subset_iterator = self.mode(self.total_n_exs,
                                    batch_size,
                                    num_batches,
                                    rng=None)

        return EmotiwArrangerIter(self,
                                  self.subset_iterator,
                                  batch_size=batch_size)

    def dump_to(self, path, batch_size=100):
        size = self.total_n_exs
        if hack:
            size = 3*batch_size
        out_X = numpy.memmap(path + '_x.npy', mode='w+', dtype=numpy.float32, shape=(size, self.img_per_seq, self.img_res[0], self.img_res[1], self.num_channels))
        out_y = numpy.memmap(path + '_y.npy', mode='w+', dtype=numpy.uint8, shape=(size, self.img_per_seq, 1))
        it = self.iterator(batch_size=batch_size)

        if not hack:
            for idx, item in enumerate(it):
                if idx % 10 == 0:
                    print idx, ':', it.num_selected

                arr = []
                for x in item[0]:
                    arr.append([y.reshape(self.img_res[0], self.img_res[1], self.num_channels) for y in x])

                item[1].shape = (len(item[1]), self.img_per_seq, 1)
                
                out_X[batch_size*idx:batch_size*(idx+1),:] = arr[:]
                out_y[batch_size*idx:batch_size*(idx+1),:] = item[1][:,:,:]

        else:
            for idx in xrange(3):
                item = it.next()
                arr = []
                for x in item[0]:
                    arr.append([y.reshape(self.img_res[0], self.img_res[1], self.num_channels) for y in x])

                out_X[batch_size*idx:batch_size*idx+batch_size,:] = arr
                for i in xrange(batch_size):
                    out_y[batch_size*idx+i] = item[1][i]

        del out_X
        del out_y
