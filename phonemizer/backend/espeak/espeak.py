# Copyright 2015-2021 Mathieu Bernard
#
# This file is part of phonemizer: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Phonemizer is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phonemizer. If not, see <http://www.gnu.org/licenses/>.
"""Espeak backend for the phonemizer"""

import itertools
import re

from phonemizer.backend.espeak.base import BaseEspeakBackend
from phonemizer.backend.espeak.wrapper import EspeakWrapper
from phonemizer.backend.espeak.language_switch import (
    get_language_switch_processor)
from phonemizer.logger import get_logger
from phonemizer.punctuation import Punctuation


class EspeakBackend(BaseEspeakBackend):
    """Espeak backend for the phonemizer"""
    # a regular expression to find phonemes stresses in espeak output
    _ESPEAK_STRESS_RE = re.compile(r"[ˈˌ'-]+")

    # pylint: disable=too-many-arguments
    def __init__(self, language,
                 punctuation_marks=Punctuation.default_marks(),
                 preserve_punctuation=False,
                 with_stress=False,
                 tie=False,
                 language_switch='keep-flags',
                 logger=get_logger()):
        super().__init__(
            language, punctuation_marks=punctuation_marks,
            preserve_punctuation=preserve_punctuation, logger=logger)

        self._espeak.set_voice(language)
        self._with_stress = with_stress
        self._tie = self._init_tie(tie)
        self._lang_switch = get_language_switch_processor(
            language_switch, self.logger, self.language)

    @staticmethod
    def _init_tie(tie):
        if not tie:
            return False

        if tie is True:  # default U+361 tie character
            return '͡'

        # non default tie charcacter
        tie = str(tie)
        if len(tie) != 1:
            raise RuntimeError(
                f'explicit tie must be a single charcacter but is {tie}')
        return tie

    @staticmethod
    def name():
        return 'espeak'

    @classmethod
    def supported_languages(cls):
        return {
            voice.language: voice.name
            for voice in EspeakWrapper().available_voices()}

    def _phonemize_aux(self, text, offset, separator, strip):
        output = []
        lang_switches = []
        for num, line in enumerate(text.split('\n'), start=1):
            line = self._espeak.text_to_phonemes(line)
            line, has_switch = self._postprocess_line(
                line, num, separator, strip)
            output.append(line)
            if has_switch:
                lang_switches.append(num + offset)

        return output, lang_switches

    def _process_stress(self, word):
        if self._with_stress:
            return word
        # remove the stresses on phonemes
        return re.sub(self._ESPEAK_STRESS_RE, '', word)

    def _process_tie(self, word, separator):
        if self._tie:
            # merge consecutive chars of a phone with self._tie
            return separator.phone.join(
                self._tie.join(phn) for phn in word.split('_'))
        return word.replace('_', separator.phone)

    def _postprocess_line(self, line, num, separator, strip):
        # espeak can split an utterance into several lines because
        # of punctuation, here we merge the lines into a single one
        line = line.strip().replace('\n', ' ').replace('  ', ' ')

        # due to a bug in espeak-ng, some additional separators can be
        # added at the end of a word. Here a quick fix to solve that
        # issue. See https://github.com/espeak-ng/espeak-ng/issues/694
        line = re.sub(r'_+', '_', line)
        line = re.sub(r'_ ', ' ', line)

        line, has_switch = self._lang_switch.process(line)
        if not line:
            return '', has_switch

        out_line = ''
        for word in line.split(' '):
            word = self._process_stress(word.strip())
            word = self._process_tie(word if strip else word + '_', separator)
            out_line += word + separator.word

        if strip and separator.word:
            # erase the last word separator from the line
            out_line = out_line[:-len(separator.word)]

        return out_line, has_switch

    def _phonemize_postprocess(self, phonemized, text_type, punctuation_marks):
        text = phonemized[0]
        switches = phonemized[1]
        self._lang_switch.warning(switches)
        return super()._phonemize_postprocess(
            text, text_type, punctuation_marks)

    @staticmethod
    def _flatten(phonemized):
        # TODO optimize, test and comment
        flattened = []
        for i in range(len(phonemized[0])):
            flattened.append(
                list(itertools.chain(
                    c for chunk in phonemized for c in chunk[i])))
        return flattened